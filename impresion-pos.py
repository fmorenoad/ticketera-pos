import win32print
import win32ui
import qrcode
import json
import os
from PIL import Image, ImageWin
from flask import Flask, request, jsonify
from flask_cors import CORS  # Permitir solicitudes desde Laravel
from datetime import datetime
import time

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})  # Habilitar CORS para todas las rutas

# ------------------------------------------------------------------
# Plantillas de ticket
# ------------------------------------------------------------------
TEMPLATES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates.json")

# Formato usado cuando la web no envia template_id (compatibilidad con version anterior)
DEFAULT_TEMPLATE = {
    "nombre": "Por defecto",
    "titulo": "TODOS GANAN",
    "subtitulo": "",
    "mostrar_borde": True,
    "mostrar_qr": True,
    "mostrar_producto": True,
    "mostrar_codigo": True,
    "mostrar_fecha": True,
    "pie": "",
}

# Campos que una plantilla puede definir; todo lo demas se ignora
CAMPOS_PLANTILLA = list(DEFAULT_TEMPLATE.keys())


def cargar_templates():
    """ Lee templates.json; estructura: {"next_id": int, "templates": {id: config}} """
    if not os.path.exists(TEMPLATES_FILE):
        return {"next_id": 1, "templates": {}}
    try:
        with open(TEMPLATES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"next_id": 1, "templates": {}}


def guardar_templates(data):
    with open(TEMPLATES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def normalizar_plantilla(payload):
    """ Toma solo los campos conocidos y completa con los valores por defecto """
    plantilla = dict(DEFAULT_TEMPLATE)
    for campo in CAMPOS_PLANTILLA:
        if campo in payload:
            plantilla[campo] = payload[campo]
    return plantilla

def centrar_texto(pdc, texto):
    """ Calcula la posición X para centrar un texto en la impresora """
    printer_width = pdc.GetDeviceCaps(8)
    text_width, _ = pdc.GetTextExtent(texto)
    return (printer_width - text_width) // 2

def generar_qr(code):
    """ Genera un código QR y lo devuelve como una imagen DIB """
    qr = qrcode.make(code)
    qr_path = "qr_temp.bmp"
    qr.save(qr_path)
    qr_image = Image.open(qr_path)
    return ImageWin.Dib(qr_image)

def centrar_qr(pdc, qr_size=400):
    """ Calcula la posición X para centrar un código QR """
    printer_width = pdc.GetDeviceCaps(8)
    return (printer_width - qr_size) // 2

def mover_y(y, espacio=30):
    """ Aumenta la posición en Y para hacer un salto de línea """
    return y + espacio

def imprimir_ticket(ticket, plantilla=None):
    """ Imprime UN ticket usando la plantilla indicada (o la por defecto) """

    if plantilla is None:
        plantilla = DEFAULT_TEMPLATE

    # Variables
    qr_size = 400
    x = 10
    y = 100

    # Definir fuentes
    normal_font = win32ui.CreateFont({
        "name": "Arial",
        "height": 30,
        "weight": 400
    })
    title_font = win32ui.CreateFont({
        "name": "Arial",
        "height": 60,
        "weight": 700
    })
    subtitle_font = win32ui.CreateFont({
        "name": "Arial",
        "height": 40,
        "weight": 500
    })
    product_font = win32ui.CreateFont({
        "name": "Arial",
        "height": 55,
        "weight": 500
    })

    # Configurar impresora
    printer_name = win32print.GetDefaultPrinter()
    hprinter = win32print.OpenPrinter(printer_name)
    pdc = win32ui.CreateDC()
    pdc.CreatePrinterDC(printer_name)
    pdc.StartDoc('Ticket')
    pdc.StartPage()

    borde = "***************************"

    # Encabezado
    pdc.SelectObject(title_font)
    if plantilla.get("mostrar_borde"):
        pdc.TextOut(x, y, borde)
        y = mover_y(y)

    titulo = plantilla.get("titulo") or ""
    if titulo:
        pdc.TextOut(centrar_texto(pdc, titulo), y, titulo)
        y = mover_y(y, 50)

    if plantilla.get("mostrar_borde"):
        pdc.TextOut(x, y, borde)
        y = mover_y(y, 50)

    subtitulo = plantilla.get("subtitulo") or ""
    if subtitulo:
        pdc.SelectObject(subtitle_font)
        pdc.TextOut(centrar_texto(pdc, subtitulo), y, subtitulo)
        y = mover_y(y, 50)

    # QR centrado
    if plantilla.get("mostrar_qr"):
        hbm = generar_qr(ticket["id"])
        center_x_qr = centrar_qr(pdc, qr_size)
        y = mover_y(y, 20)
        hbm.draw(pdc.GetHandleOutput(), (center_x_qr, y, center_x_qr + qr_size, y + qr_size))
        y = mover_y(y, qr_size)

    # Nombre del producto centrado
    if plantilla.get("mostrar_producto"):
        pdc.SelectObject(product_font)
        pdc.TextOut(centrar_texto(pdc, ticket["product"]), y, ticket["product"])
        y = mover_y(y, 70)

    # Codigo y fecha centrados
    pdc.SelectObject(normal_font)
    if plantilla.get("mostrar_codigo"):
        pdc.TextOut(centrar_texto(pdc, ticket["id"]), y, ticket["id"])
        y = mover_y(y, 30)
    if plantilla.get("mostrar_fecha"):
        pdc.TextOut(centrar_texto(pdc, ticket["fecha_venta"]), y, ticket["fecha_venta"])
        y = mover_y(y, 30)

    # Pie del ticket
    pie = plantilla.get("pie") or ""
    if pie:
        y = mover_y(y, 20)
        pdc.TextOut(centrar_texto(pdc, pie), y, pie)
        y = mover_y(y, 30)

    # Finalizar impresión
    pdc.EndPage()
    pdc.EndDoc()
    pdc.DeleteDC()

    print(f"✅ Ticket {ticket['id']} impreso correctamente")

def imprimir_resumen(cantidad_tickets):
    """ Imprime un resumen después de imprimir todos los tickets """

    # Pequeña espera para liberar la impresora
    time.sleep(1)

    # Obtener la hora actual
    hora_impresion = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Variables
    x = 10
    y = 100

    # Definir fuente
    normal_font = win32ui.CreateFont({
        "name": "Arial",
        "height": 30,
        "weight": 300  # Negrita
    })
    
    title_font = win32ui.CreateFont({
        "name": "Arial",
        "height": 50,
        "weight": 700
    })

    # Configurar impresora
    printer_name = win32print.GetDefaultPrinter()
    hprinter = win32print.OpenPrinter(printer_name)
    pdc = win32ui.CreateDC()
    pdc.CreatePrinterDC(printer_name)
    pdc.StartDoc('Resumen')
    pdc.StartPage()

    # Imprimir resumen
    pdc.SelectObject(title_font)
    pdc.TextOut(centrar_texto(pdc, "COMPROBANTE DE VENTA"), y, "COMPROBANTE DE VENTA")
    y = mover_y(y, 50)
    
    pdc.SelectObject(normal_font)

    pdc.TextOut(centrar_texto(pdc, f"Total Tickets: {cantidad_tickets}"), y, f"Total Tickets: {cantidad_tickets}")
    y = mover_y(y, 30)

    pdc.TextOut(centrar_texto(pdc, f"Hora de Impresión: {hora_impresion}"), y, f"Hora de Impresión: {hora_impresion}")
    y = mover_y(y, 30)

    pdc.EndPage()
    pdc.EndDoc()
    pdc.DeleteDC()

    print(f"📄 Resumen impreso: {cantidad_tickets} tickets, Hora: {hora_impresion}")
    
def imprimir_ticket_cierre_turno(titulo, datos):
    """ Imprime un ticket genérico con título y datos """

    x = 10
    y = 100

    # Definir fuentes
    title_font = win32ui.CreateFont({"name": "Arial", "height": 50, "weight": 700})
    normal_font = win32ui.CreateFont({"name": "Arial", "height": 30, "weight": 500})
    amount_font = win32ui.CreateFont({"name": "Arial", "height": 50, "weight": 600})
    manager_font = win32ui.CreateFont({"name": "Arial", "height": 30, "weight": 500})

    # Configurar impresora
    printer_name = win32print.GetDefaultPrinter()
    hprinter = win32print.OpenPrinter(printer_name)
    pdc = win32ui.CreateDC()
    pdc.CreatePrinterDC(printer_name)
    pdc.StartDoc(titulo)
    pdc.StartPage()

    # Imprimir encabezado
    pdc.SelectObject(title_font)
    pdc.TextOut(centrar_texto(pdc, titulo), y, titulo)
    y = mover_y(y, 60)
    pdc.SelectObject(normal_font)
    texto = " -----------------------------------------------"
    pdc.TextOut(centrar_texto(pdc, texto), y, texto)
    y = mover_y(y, 100)
    
    
    texto = f"ID de Turno: {datos['turn_id']}"
    pdc.TextOut(x, y, texto)
    y = mover_y(y, 30)
        
    texto = f"Fecha de Turno: {datos['fecha']}"
    pdc.TextOut(x, y, texto)
    y = mover_y(y, 30)
    
    texto = f"Fecha inicio de Turno: {datos['fecha_inicio']}"
    pdc.TextOut(x, y, texto)
    y = mover_y(y, 30)
    
    texto = f"Fecha fin de Turno: {datos['fecha_fin']}"
    pdc.TextOut(x, y, texto)
    y = mover_y(y, 30)
    
    texto = f"Usuario: {datos['user']}"
    pdc.TextOut(x, y, texto)
    y = mover_y(y, 30)
    
    
    pdc.SelectObject(amount_font)  
    texto = " -----------------------------------------------"
    pdc.TextOut(centrar_texto(pdc, texto), y, texto)
    y = mover_y(y, 70)
    
    texto = f"Inicial en caja: ${datos['inicial_caja']}"
    pdc.TextOut(x, y, texto)
    y = mover_y(y, 50)
    
    pdc.SelectObject(amount_font)    
    texto = f"Total vendido: ${datos['total_recaudado']}"
    pdc.TextOut(x, y, texto)
    y = mover_y(y, 50)
    
    pdc.SelectObject(amount_font)    
    texto = f"Total retiros: ${datos['entregas']}"
    pdc.TextOut(x, y, texto)
    y = mover_y(y, 50)
    
    pdc.SelectObject(amount_font)    
    texto = f"Entrega final: ${datos['entrega_final']}"
    pdc.TextOut(x, y, texto)
    y = mover_y(y, 70)
    
    texto = " -----------------------------------------------"
    pdc.TextOut(centrar_texto(pdc, texto), y, texto)
    
    y = mover_y(y, 100)
    
    pdc.SelectObject(manager_font)
    texto = "Retira: _________________________________"
    pdc.TextOut(x, y, texto)
    y = mover_y(y, 150)
    texto = "Firma: _________________________________"
    pdc.TextOut(x, y, texto)
    y = mover_y(y, 150)
    # Imprimir cada línea de datos
    
    
    # pdc.TextOut(centrar_texto(pdc, line), y, line)
    # y = mover_y(y, 30)
    # for key, value in datos.items():
    #     line = f"{key}: {value}"
    #     pdc.TextOut(centrar_texto(pdc, line), y, line)
    #     y = mover_y(y, 30)

    # Finalizar impresión
    pdc.EndPage()
    pdc.EndDoc()
    pdc.DeleteDC()

    print(f"✅ {titulo} impreso correctamente")
    
def imprimir_ticket_retiro(titulo, datos):
    """ Imprime un ticket genérico con título y datos """

    x = 10
    y = 100

    # Definir fuentes
    title_font = win32ui.CreateFont({"name": "Arial", "height": 50, "weight": 700})
    normal_font = win32ui.CreateFont({"name": "Arial", "height": 30, "weight": 500})
    amount_font = win32ui.CreateFont({"name": "Arial", "height": 50, "weight": 600})
    manager_font = win32ui.CreateFont({"name": "Arial", "height": 30, "weight": 500})

    # Configurar impresora
    printer_name = win32print.GetDefaultPrinter()
    hprinter = win32print.OpenPrinter(printer_name)
    pdc = win32ui.CreateDC()
    pdc.CreatePrinterDC(printer_name)
    pdc.StartDoc(titulo)
    pdc.StartPage()

    # Imprimir encabezado
    pdc.SelectObject(title_font)
    pdc.TextOut(centrar_texto(pdc, titulo), y, titulo)
    y = mover_y(y, 60)
    pdc.SelectObject(normal_font)
    texto = " -----------------------------------------------"
    pdc.TextOut(centrar_texto(pdc, texto), y, texto)
    y = mover_y(y, 150)
    
    
    texto = f"ID de Turno: {datos['turno_id']}"
    pdc.TextOut(x, y, texto)
    y = mover_y(y, 30)
    
    texto = f"ID de Retiro: {datos['retiro_id']}"
    pdc.TextOut(x, y, texto)
    y = mover_y(y, 30)
    
    texto = f"Fecha de Turno: {datos['turno_date']}"
    pdc.TextOut(x, y, texto)
    y = mover_y(y, 30)
    
    texto = f"Usuario: {datos['usuario']}"
    pdc.TextOut(x, y, texto)
    y = mover_y(y, 30)
    
    pdc.SelectObject(amount_font)    
    texto = f"Monto retirado: {datos['monto_retirado']}"
    pdc.TextOut(x, y, texto)
    y = mover_y(y, 100)
    
    pdc.SelectObject(manager_font)
    texto = "Retira: _________________________________"
    pdc.TextOut(x, y, texto)
    y = mover_y(y, 150)
    texto = "Firma: _________________________________"
    pdc.TextOut(x, y, texto)
    y = mover_y(y, 150)
    # Imprimir cada línea de datos
    
    
    # pdc.TextOut(centrar_texto(pdc, line), y, line)
    # y = mover_y(y, 30)
    # for key, value in datos.items():
    #     line = f"{key}: {value}"
    #     pdc.TextOut(centrar_texto(pdc, line), y, line)
    #     y = mover_y(y, 30)

    # Finalizar impresión
    pdc.EndPage()
    pdc.EndDoc()
    pdc.DeleteDC()

    print(f"✅ {titulo} impreso correctamente")
@app.route('/templates', methods=['POST'])
def recibir_template():
    """ Recibe una plantilla desde la web, la guarda y devuelve su id.
        Si el payload trae template_id y existe, la actualiza manteniendo el id. """
    try:
        payload = request.json
        if not payload or not isinstance(payload, dict):
            return jsonify({"status": "error", "message": "Formato incorrecto, se espera un objeto JSON"}), 400

        plantilla = normalizar_plantilla(payload)

        if not plantilla["titulo"] and not plantilla["subtitulo"]:
            return jsonify({"status": "error", "message": "La plantilla debe tener al menos un título o subtítulo"}), 422

        data = cargar_templates()

        template_id = str(payload.get("template_id") or "")
        if template_id and template_id in data["templates"]:
            data["templates"][template_id] = plantilla
            mensaje = f"Plantilla {template_id} actualizada"
        else:
            template_id = str(data["next_id"])
            data["next_id"] += 1
            data["templates"][template_id] = plantilla
            mensaje = f"Plantilla {template_id} registrada"

        guardar_templates(data)
        print(f"📋 {mensaje}: {plantilla['nombre']}")

        return jsonify({"status": "success", "message": mensaje, "template_id": template_id})

    except Exception as e:
        print(f"❌ Error al guardar plantilla: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/templates', methods=['GET'])
def listar_templates():
    """ Lista las plantillas registradas en este POS """
    data = cargar_templates()
    return jsonify({"status": "success", "templates": data["templates"]})


@app.route('/print', methods=['POST'])
def receive_tickets():
    """ API Flask para recibir tickets y enviarlos a la impresora.
        Acepta {"template_id": id, "tickets": [...]} o una lista simple
        de tickets (formato antiguo, usa la plantilla por defecto). """
    try:
        data = request.json

        plantilla = None
        if isinstance(data, dict):
            template_id = str(data.get("template_id") or "")
            tickets = data.get("tickets")

            if not template_id:
                return jsonify({"status": "error", "message": "Falta el template_id"}), 400

            registradas = cargar_templates()["templates"]
            if template_id not in registradas:
                return jsonify({"status": "error", "message": f"La plantilla {template_id} no está registrada en este POS. Envíala desde la web antes de imprimir."}), 404

            plantilla = registradas[template_id]
        else:
            tickets = data  # Formato antiguo: lista de tickets sin plantilla

        if not tickets or not isinstance(tickets, list):
            return jsonify({"status": "error", "message": "Formato incorrecto, se espera una lista de tickets"}), 400

        for ticket in tickets:
            imprimir_ticket(ticket, plantilla)

        # Esperar a que la impresora libere la cola antes de imprimir el resumen
        time.sleep(1)

        # Imprimir resumen al final
        #imprimir_resumen(len(tickets))

        return jsonify({"status": "success", "message": f"Se imprimieron {len(tickets)} tickets"})

    except Exception as e:
        print(f"❌ Error en la API: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/print/retiro', methods=['POST'])
def imprimir_retiro():
    """ API para imprimir un comprobante de retiro de dinero """
    try:
        retiro = request.json
        if not retiro or not isinstance(retiro, dict):
            return jsonify({"status": "error", "message": "Formato incorrecto, se espera un objeto JSON"}), 400

        imprimir_ticket_retiro("RETIRO DE DINERO", retiro)
        imprimir_ticket_retiro("RETIRO DE DINERO", retiro)
        return jsonify({"status": "success", "message": "Comprobante de retiro impreso"})

    except Exception as e:
        print(f"❌ Error al imprimir retiro: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/print/cierre', methods=['POST'])
def imprimir_cierre():
    """ API para imprimir un comprobante de cierre de caja """
    try:
        cierre_turno = request.json
        if not cierre_turno or not isinstance(cierre_turno, dict):
            return jsonify({"status": "error", "message": "Formato incorrecto, se espera un objeto JSON"}), 400

        imprimir_ticket_cierre_turno("CIERRE DE TURNO", cierre_turno)
        imprimir_ticket_cierre_turno("CIERRE DE TURNO", cierre_turno)
        return jsonify({"status": "success", "message": "Comprobante de cierre impreso"})

    except Exception as e:
        print(f"❌ Error al imprimir cierre de caja: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    
if __name__ == '__main__':
    print("🔥 API de impresión ejecutándose en http://127.0.0.1:5000/")
    app.run(host='0.0.0.0', port=5000)