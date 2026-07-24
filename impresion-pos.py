import win32print
import win32ui
import qrcode
import json
import os
import urllib.request
import urllib.error
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

# ------------------------------------------------------------------
# Impresora
# ------------------------------------------------------------------
IMPRESORA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "impresora.txt")


def obtener_impresora():
    """ Impresora a usar: la indicada en impresora.txt (junto al script),
        o la predeterminada de Windows si el archivo no existe. """
    if os.path.exists(IMPRESORA_FILE):
        # utf-8-sig tolera el BOM que agregan el Bloc de notas y PowerShell
        with open(IMPRESORA_FILE, "r", encoding="utf-8-sig") as f:
            nombre = f.read().strip()
        if nombre:
            return nombre
    return win32print.GetDefaultPrinter()


def impresoras_instaladas():
    """ Nombres de todas las impresoras que reconoce Windows """
    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    return [p[2] for p in win32print.EnumPrinters(flags)]


# ------------------------------------------------------------------
# Servidor de la ticketera (para sincronizar la plantilla activa)
# ------------------------------------------------------------------
SERVIDOR_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "servidor.txt")
SERVIDOR_DEFAULT = "https://ticketera.iwan.cl"


def obtener_servidor():
    """ URL del servidor: la de servidor.txt (junto al script) o la por defecto """
    if os.path.exists(SERVIDOR_FILE):
        with open(SERVIDOR_FILE, "r", encoding="utf-8-sig") as f:
            url = f.read().strip()
        if url:
            return url.rstrip("/")
    return SERVIDOR_DEFAULT


def guardar_plantilla_sincronizada(almacen, template_id, nombre, config):
    """ Upsert de una plantilla del servidor en el almacen local.
        Devuelve 'nueva', 'actualizada' o 'al_dia'. """
    payload = dict(config or {})
    payload["nombre"] = nombre or "Plantilla"
    plantilla = normalizar_plantilla(payload)

    anterior = almacen["templates"].get(template_id)
    almacen["templates"][template_id] = plantilla

    if template_id.isdigit() and int(template_id) >= almacen["next_id"]:
        almacen["next_id"] = int(template_id) + 1

    if anterior is None:
        return "nueva"
    if anterior != plantilla:
        return "actualizada"
    return "al_dia"


def sincronizar_plantillas():
    """ Descarga TODAS las plantillas del servidor (la activa al final,
        para que prevalezca ante ids en conflicto). Si el servidor es
        antiguo y no tiene el endpoint, cae al de plantilla activa. """
    url = obtener_servidor() + "/api/plantillas"

    try:
        with urllib.request.urlopen(url, timeout=8) as respuesta:
            data = json.loads(respuesta.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print("[SYNC] Servidor sin endpoint de catalogo; sincronizando solo la activa.")
            return sincronizar_plantilla_activa()
        mensaje = f"El servidor respondio {e.code}; se usan las plantillas locales."
        print(f"[SYNC] {mensaje}")
        return {"sincronizada": False, "mensaje": mensaje}
    except Exception as e:
        mensaje = f"Sin conexion con el servidor ({e}); se usan las plantillas locales."
        print(f"[SYNC] {mensaje}")
        return {"sincronizada": False, "mensaje": mensaje}

    lista = data.get("templates") or []

    if not lista:
        mensaje = "El servidor no tiene plantillas registradas en POS todavia."
        print(f"[SYNC] {mensaje}")
        return {"sincronizada": True, "total": 0, "mensaje": mensaje}

    # La activa se aplica al final para que gane ante ids duplicados
    lista.sort(key=lambda t: 1 if t.get("active") else 0)

    almacen = cargar_templates()
    nuevas = 0
    actualizadas = 0

    for t in lista:
        template_id = str(t.get("template_id") or "")
        if not template_id:
            continue

        resultado = guardar_plantilla_sincronizada(almacen, template_id, t.get("nombre"), t.get("config"))

        if resultado == "nueva":
            nuevas += 1
        elif resultado == "actualizada":
            actualizadas += 1

    guardar_templates(almacen)

    mensaje = f"{len(lista)} plantillas del servidor: {nuevas} nuevas, {actualizadas} actualizadas, {len(lista) - nuevas - actualizadas} al dia."
    print(f"[SYNC] {mensaje}")

    return {"sincronizada": True, "total": len(lista), "nuevas": nuevas, "actualizadas": actualizadas, "mensaje": mensaje}


def sincronizar_plantilla_activa():
    """ Consulta al servidor cual es la plantilla activa y actualiza (o
        descarga) la copia local para que coincida con la web. """
    url = obtener_servidor() + "/api/plantilla-activa"

    try:
        with urllib.request.urlopen(url, timeout=8) as respuesta:
            data = json.loads(respuesta.read().decode("utf-8"))
    except Exception as e:
        mensaje = f"Sin conexion con el servidor ({e}); se usan las plantillas locales."
        print(f"[SYNC] {mensaje}")
        return {"sincronizada": False, "mensaje": mensaje}

    if not data.get("active"):
        mensaje = "El servidor no tiene plantilla activa; se usa el formato por defecto."
        print(f"[SYNC] {mensaje}")
        return {"sincronizada": False, "mensaje": mensaje}

    template_id = str(data.get("template_id") or "")

    if not template_id:
        mensaje = "La plantilla activa del servidor aun no tiene id de POS (enviala desde la web una vez)."
        print(f"[SYNC] {mensaje}")
        return {"sincronizada": False, "mensaje": mensaje}

    payload = dict(data.get("config") or {})
    payload["nombre"] = data.get("nombre") or "Plantilla activa"
    plantilla = normalizar_plantilla(payload)

    almacen = cargar_templates()
    anterior = almacen["templates"].get(template_id)
    almacen["templates"][template_id] = plantilla

    if template_id.isdigit() and int(template_id) >= almacen["next_id"]:
        almacen["next_id"] = int(template_id) + 1

    guardar_templates(almacen)

    if anterior is None:
        mensaje = f"Plantilla activa {template_id} ('{plantilla['nombre']}') descargada del servidor."
    elif anterior != plantilla:
        mensaje = f"Plantilla activa {template_id} ('{plantilla['nombre']}') actualizada desde el servidor."
    else:
        mensaje = f"Plantilla activa {template_id} ('{plantilla['nombre']}') ya estaba al dia."

    print(f"[SYNC] {mensaje}")
    return {"sincronizada": True, "template_id": template_id, "mensaje": mensaje}


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
    """ Calcula la posicion X para centrar un texto en la impresora """
    printer_width = pdc.GetDeviceCaps(8)
    text_width, _ = pdc.GetTextExtent(texto)
    return (printer_width - text_width) // 2


def generar_qr(code):
    """ Genera un codigo QR y lo devuelve como una imagen DIB """
    qr = qrcode.make(code)
    qr_path = "qr_temp.bmp"
    qr.save(qr_path)
    qr_image = Image.open(qr_path)
    return ImageWin.Dib(qr_image)


def centrar_qr(pdc, qr_size=400):
    """ Calcula la posicion X para centrar un codigo QR """
    printer_width = pdc.GetDeviceCaps(8)
    return (printer_width - qr_size) // 2


def mover_y(y, espacio=30):
    """ Aumenta la posicion en Y para hacer un salto de linea """
    return y + espacio


def imprimir_ticket(ticket, plantilla=None):
    """ Imprime UN ticket usando la plantilla indicada (o la por defecto) """

    if plantilla is None:
        plantilla = DEFAULT_TEMPLATE

    # Variables
    qr_size = 400
    x = 10
    y = 15  # margen superior minimo

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
    printer_name = obtener_impresora()
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

    # Finalizar impresion
    pdc.EndPage()
    pdc.EndDoc()
    pdc.DeleteDC()

    print(f"[OK] Ticket {ticket['id']} impreso correctamente")


def imprimir_resumen(cantidad_tickets):
    """ Imprime un resumen despues de imprimir todos los tickets """

    # Pequena espera para liberar la impresora
    time.sleep(1)

    # Obtener la hora actual
    hora_impresion = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Variables
    x = 10
    y = 15  # margen superior minimo

    # Definir fuente
    normal_font = win32ui.CreateFont({
        "name": "Arial",
        "height": 30,
        "weight": 300
    })

    title_font = win32ui.CreateFont({
        "name": "Arial",
        "height": 50,
        "weight": 700
    })

    # Configurar impresora
    printer_name = obtener_impresora()
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

    pdc.TextOut(centrar_texto(pdc, f"Hora de Impresion: {hora_impresion}"), y, f"Hora de Impresion: {hora_impresion}")
    y = mover_y(y, 30)

    pdc.EndPage()
    pdc.EndDoc()
    pdc.DeleteDC()

    print(f"[OK] Resumen impreso: {cantidad_tickets} tickets, Hora: {hora_impresion}")


def imprimir_ticket_cierre_turno(titulo, datos):
    """ Imprime el comprobante de cierre de turno """

    x = 10
    y = 15  # margen superior minimo

    # Definir fuentes
    title_font = win32ui.CreateFont({"name": "Arial", "height": 50, "weight": 700})
    normal_font = win32ui.CreateFont({"name": "Arial", "height": 30, "weight": 500})
    amount_font = win32ui.CreateFont({"name": "Arial", "height": 50, "weight": 600})
    manager_font = win32ui.CreateFont({"name": "Arial", "height": 30, "weight": 500})

    # Configurar impresora
    printer_name = obtener_impresora()
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

    # Finalizar impresion
    pdc.EndPage()
    pdc.EndDoc()
    pdc.DeleteDC()

    print(f"[OK] {titulo} impreso correctamente")


def imprimir_ticket_retiro(titulo, datos):
    """ Imprime el comprobante de retiro de dinero """

    x = 10
    y = 15  # margen superior minimo

    # Definir fuentes
    title_font = win32ui.CreateFont({"name": "Arial", "height": 50, "weight": 700})
    normal_font = win32ui.CreateFont({"name": "Arial", "height": 30, "weight": 500})
    amount_font = win32ui.CreateFont({"name": "Arial", "height": 50, "weight": 600})
    manager_font = win32ui.CreateFont({"name": "Arial", "height": 30, "weight": 500})

    # Configurar impresora
    printer_name = obtener_impresora()
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

    # Finalizar impresion
    pdc.EndPage()
    pdc.EndDoc()
    pdc.DeleteDC()

    print(f"[OK] {titulo} impreso correctamente")


@app.route('/status', methods=['GET'])
def estado():
    """ Diagnostico: impresora configurada, si Windows la reconoce y plantillas """
    impresora = obtener_impresora()
    instaladas = impresoras_instaladas()

    return jsonify({
        "status": "success",
        "impresora": impresora,
        "impresora_disponible": impresora in instaladas,
        "impresoras_instaladas": instaladas,
        "config_por_archivo": os.path.exists(IMPRESORA_FILE),
        "plantillas_registradas": len(cargar_templates()["templates"]),
        "servidor": obtener_servidor(),
    })


@app.route('/templates/sync', methods=['POST'])
def sincronizar_endpoint():
    """ Re-sincroniza todas las plantillas desde el servidor sin reiniciar """
    resultado = sincronizar_plantillas()
    return jsonify({"status": "success", **resultado})


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
            return jsonify({"status": "error", "message": "La plantilla debe tener al menos un titulo o subtitulo"}), 422

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
        print(f"[TPL] {mensaje}: {plantilla['nombre']}")

        return jsonify({"status": "success", "message": mensaje, "template_id": template_id})

    except Exception as e:
        print(f"[ERROR] Al guardar plantilla: {e}")
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
                return jsonify({"status": "error", "message": f"La plantilla {template_id} no esta registrada en este POS. Enviala desde la web antes de imprimir."}), 404

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
        print(f"[ERROR] En la API: {e}")
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
        print(f"[ERROR] Al imprimir retiro: {e}")
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
        print(f"[ERROR] Al imprimir cierre de caja: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == '__main__':
    impresora = obtener_impresora()
    disponible = impresora in impresoras_instaladas()
    origen = "impresora.txt" if os.path.exists(IMPRESORA_FILE) else "predeterminada de Windows"

    print("=" * 55)
    print("API de impresion ticketera-pos - http://127.0.0.1:5000/")
    print(f"Impresora ({origen}): {impresora}")
    print("Reconocida por Windows: " + ("SI" if disponible else "NO - revisar conexion o impresora.txt"))
    print(f"Servidor: {obtener_servidor()}")
    print("=" * 55)

    # Alinear las plantillas con la web antes de empezar a imprimir
    sincronizar_plantillas()

    app.run(host='0.0.0.0', port=5000)
