from flask import Flask, jsonify, request, render_template
import json
import random
import os
import threading
import time
from datetime import datetime

app = Flask(__name__)
DB_FILE = 'parqueo.json'

# ============================================================
# BASE DE DATOS DE PLACAS AUTORIZADAS
# Vehiculos registrados en el sistema de la UPB
# ============================================================
PLACAS_AUTORIZADAS = [
    {"placa": "ABC-123", "propietario": "Juan Perez", "tipo": "Estudiante", "zona_permitida": "H"},
    {"placa": "DEF-456", "propietario": "Maria Lopez", "tipo": "Estudiante", "zona_permitida": "G"},
    {"placa": "GHI-789", "propietario": "Carlos Rojas", "tipo": "Docente", "zona_permitida": "F"},
    {"placa": "JKL-012", "propietario": "Ana Torres", "tipo": "Estudiante", "zona_permitida": "H"},
    {"placa": "MNO-345", "propietario": "Luis Gomez", "tipo": "Docente", "zona_permitida": "E"},
    {"placa": "PQR-678", "propietario": "Sofia Ruiz", "tipo": "Estudiante", "zona_permitida": "G"},
    {"placa": "STU-901", "propietario": "Pedro Diaz", "tipo": "Administrativo", "zona_permitida": "F"},
    {"placa": "VWX-234", "propietario": "Elena Vargas", "tipo": "Estudiante", "zona_permitida": "H"},
    {"placa": "YZA-567", "propietario": "Mario Cruz", "tipo": "Docente", "zona_permitida": "E"},
    {"placa": "BCD-890", "propietario": "Lucia Mendoza", "tipo": "Estudiante", "zona_permitida": "G"},
    {"placa": "EFG-111", "propietario": "Ramon Sosa", "tipo": "Estudiante", "zona_permitida": "F"},
    {"placa": "HIJ-222", "propietario": "Patricia Nunez", "tipo": "Administrativo", "zona_permitida": "H"},
    {"placa": "KLM-333", "propietario": "Fernando Apaza", "tipo": "Docente", "zona_permitida": "E"},
    {"placa": "NOP-444", "propietario": "Carmen Velasco", "tipo": "Estudiante", "zona_permitida": "G"},
    {"placa": "QRS-555", "propietario": "Jorge Mamani", "tipo": "Estudiante", "zona_permitida": "F"},
    {"placa": "TUV-666", "propietario": "Rosa Quispe", "tipo": "Docente", "zona_permitida": "H"},
    {"placa": "WXY-777", "propietario": "Diego Flores", "tipo": "Estudiante", "zona_permitida": "E"},
    {"placa": "ZAB-888", "propietario": "Viviana Choque", "tipo": "Administrativo", "zona_permitida": "G"},
    {"placa": "CDE-999", "propietario": "Marco Pinto", "tipo": "Estudiante", "zona_permitida": "F"},
    {"placa": "FGH-000", "propietario": "Adriana Mejia", "tipo": "Docente", "zona_permitida": "H"},
]

# Placas NO autorizadas que aparecen aleatoriamente en la camara
PLACAS_NO_AUTORIZADAS = [
    {"placa": "XYZ-999", "motivo": "Vehiculo no registrado en el sistema UPB"},
    {"placa": "WWW-111", "motivo": "Vehiculo no registrado en el sistema UPB"},
    {"placa": "QQQ-222", "motivo": "Acceso temporalmente suspendido"},
    {"placa": "ZZZ-333", "motivo": "Vehiculo no registrado en el sistema UPB"},
    {"placa": "RRR-444", "motivo": "Cuota de parqueo pendiente"},
]

# ============================================================
# ESTADO GLOBAL DE LA SIMULACION
# ============================================================
simulacion_activa = False
simulacion_thread = None
simulacion_lock = threading.Lock()

# Cola de eventos para el frontend
eventos_recientes = []
MAX_EVENTOS = 50

# Estado de la camara LPR
camara_lpr = {
    "activa": False,
    "ultima_placa_detectada": None,
    "ultimo_estado": None,  # "autorizado", "denegado", "esperando"
    "ultima_deteccion": None,
    "detalle_vehiculo": None,
    "motivo_rechazo": None,
}


# ============================================================
# INICIALIZACION DE LA BASE DE DATOS
# ============================================================
def init_db():
    if not os.path.exists(DB_FILE):
        db = {
            "parqueo": {"zonas": {"H": [], "G": [], "F": [], "E": []}},
            "simulacion": {"activa": False}
        }
        for zona in ["H", "G", "F", "E"]:
            for i in range(1, 9):
                db["parqueo"]["zonas"][zona].append({
                    "id": f"{zona}-{i}",
                    "estado": "libre",
                    "placa": None,
                    "hora_ingreso": None,
                    "propietario": None,
                    "tipo": None
                })
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(db, f, indent=4, ensure_ascii=False)


def leer_db():
    with open(DB_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def guardar_db(datos):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(datos, f, indent=4, ensure_ascii=False)


# ============================================================
# UTILIDADES
# ============================================================
def registrar_evento(tipo, mensaje, placa=None, detalle=None):
    """Agrega un evento a la cola de eventos recientes."""
    evento = {
        "tipo": tipo,  # "entrada", "salida", "denegado", "sistema", "camara"
        "mensaje": mensaje,
        "placa": placa,
        "hora": datetime.now().strftime("%H:%M:%S"),
        "timestamp": time.time(),
        "detalle": detalle
    }
    eventos_recientes.insert(0, evento)
    if len(eventos_recientes) > MAX_EVENTOS:
        eventos_recientes.pop()


def buscar_placa_autorizada(placa):
    """Busca una placa en la lista de autorizadas."""
    for v in PLACAS_AUTORIZADAS:
        if v["placa"] == placa:
            return v
    return None


def obtener_espacios_libres():
    """Retorna lista de todos los espacios libres."""
    db = leer_db()
    libres = []
    for zona_id in ["H", "G", "F", "E"]:
        for espacio in db["parqueo"]["zonas"][zona_id]:
            if espacio["estado"] == "libre":
                libres.append(espacio)
    return libres


def obtener_vehiculos_estacionados():
    """Retorna lista de espacios ocupados."""
    db = leer_db()
    ocupados = []
    for zona_id in ["H", "G", "F", "E"]:
        for espacio in db["parqueo"]["zonas"][zona_id]:
            if espacio["estado"] == "ocupado":
                ocupados.append(espacio)
    return ocupados


def asignar_espacio_aleatorio(placa, vehiculo_info):
    """Asigna un espacio aleatorio libre."""
    db = leer_db()
    libres = []
    for zona_id in ["H", "G", "F", "E"]:
        for espacio in db["parqueo"]["zonas"][zona_id]:
            if espacio["estado"] == "libre":
                libres.append(espacio)

    if not libres:
        return None

    # Elegir un espacio aleatorio
    espacio_elegido = random.choice(libres)
    espacio_elegido["estado"] = "ocupado"
    espacio_elegido["placa"] = placa
    espacio_elegido["hora_ingreso"] = datetime.now().strftime("%H:%M:%S")
    espacio_elegido["propietario"] = vehiculo_info.get("propietario", "Desconocido")
    espacio_elegido["tipo"] = vehiculo_info.get("tipo", "No especificado")

    guardar_db(db)
    return espacio_elegido


def liberar_vehiculo(placa):
    """Libera el espacio de un vehiculo por placa."""
    db = leer_db()
    for zona_id in ["H", "G", "F", "E"]:
        for espacio in db["parqueo"]["zonas"][zona_id]:
            if espacio["placa"] == placa:
                espacio_liberado = dict(espacio)
                espacio["estado"] = "libre"
                espacio["placa"] = None
                espacio["hora_ingreso"] = None
                espacio["propietario"] = None
                espacio["tipo"] = None
                guardar_db(db)
                return espacio_liberado
    return None


def generar_placa_aleatoria_no_autorizada():
    """Genera una placa aleatoria que no esta autorizada."""
    return random.choice(PLACAS_NO_AUTORIZADAS)


def simular_deteccion_camara():
    """Simula la deteccion de un vehiculo por la camara LPR."""
    # 75% probabilidad de que sea autorizado, 25% no autorizado
    if random.random() < 0.75:
        vehiculo = random.choice(PLACAS_AUTORIZADAS)
        camara_lpr["ultima_placa_detectada"] = vehiculo["placa"]
        camara_lpr["ultimo_estado"] = "autorizado"
        camara_lpr["ultima_deteccion"] = datetime.now().strftime("%H:%M:%S")
        camara_lpr["detalle_vehiculo"] = vehiculo
        camara_lpr["motivo_rechazo"] = None
        return vehiculo, True
    else:
        vehiculo = generar_placa_aleatoria_no_autorizada()
        camara_lpr["ultima_placa_detectada"] = vehiculo["placa"]
        camara_lpr["ultimo_estado"] = "denegado"
        camara_lpr["ultima_deteccion"] = datetime.now().strftime("%H:%M:%S")
        camara_lpr["detalle_vehiculo"] = None
        camara_lpr["motivo_rechazo"] = vehiculo["motivo"]
        return vehiculo, False


# ============================================================
# HILO DE SIMULACION AUTOMATICA
# ============================================================
def hilo_simulacion():
    """Hilo que ejecuta la simulacion automatica de entrada/salida de vehiculos."""
    global simulacion_activa

    while simulacion_activa:
        # Decidir aleatoriamente: entrada o salida
        vehiculos_dentro = obtener_vehiculos_estacionados()

        # Si hay menos de 25 vehiculos, mas probabilidad de entrada
        # Si hay mas de 25, mas probabilidad de salida
        if len(vehiculos_dentro) < 5:
            prob_entrada = 0.90
        elif len(vehiculos_dentro) < 15:
            prob_entrada = 0.70
        elif len(vehiculos_dentro) < 25:
            prob_entrada = 0.50
        elif len(vehiculos_dentro) < 30:
            prob_entrada = 0.30
        else:
            prob_entrada = 0.10

        es_entrada = random.random() < prob_entrada

        if es_entrada:
            # === SIMULAR ENTRADA ===
            vehiculo, autorizado = simular_deteccion_camara()

            if autorizado:
                # Buscar si ya esta adentro
                ya_adentro = False
                for v in vehiculos_dentro:
                    if v["placa"] == vehiculo["placa"]:
                        ya_adentro = True
                        break

                if ya_adentro:
                    registrar_evento("camara",
                        f"Camara LPR: {vehiculo['placa']} ya se encuentra dentro del parqueo",
                        placa=vehiculo["placa"],
                        detalle={"estado": "duplicado", "vehiculo": vehiculo})
                else:
                    espacio = asignar_espacio_aleatorio(vehiculo["placa"], vehiculo)
                    if espacio:
                        registrar_evento("entrada",
                            f"ENTRADA AUTORIZADA - {vehiculo['placa']} ({vehiculo['propietario']}, {vehiculo['tipo']}) -> Espacio {espacio['id']}",
                            placa=vehiculo["placa"],
                            detalle={"espacio": espacio["id"], "vehiculo": vehiculo, "camara": True})
                    else:
                        registrar_evento("denegado",
                            f"Parqueo lleno - {vehiculo['placa']} no pudo ingresar",
                            placa=vehiculo["placa"])
            else:
                # Entrada denegada
                registrar_evento("denegado",
                    f"ACCESO DENEGADO - {vehiculo['placa']}: {vehiculo['motivo']}",
                    placa=vehiculo["placa"],
                    detalle={"motivo": vehiculo["motivo"], "camara": True})

        else:
            # === SIMULAR SALIDA ===
            if vehiculos_dentro:
                vehiculo_salida = random.choice(vehiculos_dentro)
                camara_lpr["ultima_placa_detectada"] = vehiculo_salida["placa"]
                camara_lpr["ultimo_estado"] = "salida"
                camara_lpr["ultima_deteccion"] = datetime.now().strftime("%H:%M:%S")
                camara_lpr["detalle_vehiculo"] = {
                    "propietario": vehiculo_salida.get("propietario", ""),
                    "tipo": vehiculo_salida.get("tipo", "")
                }
                camara_lpr["motivo_rechazo"] = None

                espacio = liberar_vehiculo(vehiculo_salida["placa"])
                if espacio:
                    registrar_evento("salida",
                        f"SALIDA - {vehiculo_salida['placa']} libero el espacio {espacio['id']}",
                        placa=vehiculo_salida["placa"],
                        detalle={"espacio": espacio["id"], "camara": True})

        # Esperar entre 2 y 5 segundos antes del siguiente evento
        tiempo_espera = random.uniform(2.0, 5.0)
        time.sleep(tiempo_espera)


# ============================================================
# RUTAS PRINCIPALES
# ============================================================
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/parqueo', methods=['GET'])
def get_parqueo():
    db = leer_db()
    libres = len(obtener_espacios_libres())
    ocupados = 32 - libres
    return jsonify({
        "parqueo": db["parqueo"],
        "disponibles": libres,
        "ocupados": ocupados,
        "total": 32,
        "simulacion_activa": simulacion_activa
    })


@app.route('/api/placas-autorizadas', methods=['GET'])
def get_placas_autorizadas():
    return jsonify({"placas": PLACAS_AUTORIZADAS, "total": len(PLACAS_AUTORIZADAS)})


@app.route('/api/camara', methods=['GET'])
def get_camara():
    return jsonify(camara_lpr)


@app.route('/api/eventos', methods=['GET'])
def get_eventos():
    return jsonify({"eventos": eventos_recientes})


@app.route('/api/simulacion/iniciar', methods=['POST'])
def iniciar_simulacion():
    global simulacion_activa, simulacion_thread

    if simulacion_activa:
        return jsonify({"exito": False, "mensaje": "La simulacion ya esta activa."})

    simulacion_activa = True
    camara_lpr["activa"] = True
    simulacion_thread = threading.Thread(target=hilo_simulacion, daemon=True)
    simulacion_thread.start()

    registrar_evento("sistema", "SIMULACION INICIADA - Sistema LPR activado")

    return jsonify({"exito": True, "mensaje": "Simulacion iniciada."})


@app.route('/api/simulacion/detener', methods=['POST'])
def detener_simulacion():
    global simulacion_activa

    if not simulacion_activa:
        return jsonify({"exito": False, "mensaje": "La simulacion no esta activa."})

    simulacion_activa = False
    camara_lpr["activa"] = False
    camara_lpr["ultimo_estado"] = None
    registrar_evento("sistema", "SIMULACION DETENIDA")

    return jsonify({"exito": True, "mensaje": "Simulacion detenida."})


@app.route('/api/simulacion/reset', methods=['POST'])
def reset_parqueo():
    """Reinicia todos los espacios a libre y limpia eventos."""
    global eventos_recientes

    init_db()
    eventos_recientes = []
    camara_lpr["ultima_placa_detectada"] = None
    camara_lpr["ultimo_estado"] = None
    camara_lpr["detalle_vehiculo"] = None
    camara_lpr["motivo_rechazo"] = None

    registrar_evento("sistema", "Sistema reiniciado - Todos los espacios libres")

    return jsonify({"exito": True, "mensaje": "Parqueo reiniciado."})


# ============================================================
# APIs MANUALES (por si se quieren hacer entradas manuales)
# ============================================================
@app.route('/api/lpr/entrada-manual', methods=['POST'])
def entrada_manual():
    data = request.json or {}
    placa = data.get('placa', '').upper().strip()

    if not placa:
        return jsonify({"exito": False, "mensaje": "Placa no proporcionada."})

    vehiculo = buscar_placa_autorizada(placa)

    # Actualizar camara
    camara_lpr["ultima_placa_detectada"] = placa
    camara_lpr["ultima_deteccion"] = datetime.now().strftime("%H:%M:%S")

    if not vehiculo:
        camara_lpr["ultimo_estado"] = "denegado"
        camara_lpr["detalle_vehiculo"] = None
        camara_lpr["motivo_rechazo"] = "Vehiculo no registrado en el sistema UPB"
        registrar_evento("denegado",
            f"ACCESO DENEGADO - {placa}: Vehiculo no registrado",
            placa=placa,
            detalle={"motivo": "No registrado", "camara": True})
        return jsonify({"exito": False, "mensaje": "Acceso denegado: vehiculo no autorizado."})

    camara_lpr["ultimo_estado"] = "autorizado"
    camara_lpr["detalle_vehiculo"] = vehiculo
    camara_lpr["motivo_rechazo"] = None

    # Verificar si ya esta adentro
    vehiculos_dentro = obtener_vehiculos_estacionados()
    for v in vehiculos_dentro:
        if v["placa"] == placa:
            registrar_evento("camara",
                f"Camara LPR: {placa} ya se encuentra dentro del parqueo",
                placa=placa)
            return jsonify({"exito": False, "mensaje": "Vehiculo ya se encuentra dentro."})

    espacio = asignar_espacio_aleatorio(placa, vehiculo)
    if espacio:
        registrar_evento("entrada",
            f"ENTRADA AUTORIZADA - {placa} ({vehiculo['propietario']}) -> Espacio {espacio['id']}",
            placa=placa,
            detalle={"espacio": espacio["id"], "vehiculo": vehiculo, "camara": True})
        return jsonify({"exito": True, "espacio_asignado": espacio, "vehiculo": vehiculo})
    else:
        registrar_evento("denegado", f"Parqueo lleno - {placa} no pudo ingresar", placa=placa)
        return jsonify({"exito": False, "mensaje": "Parqueo lleno."})


@app.route('/api/lpr/salida-manual', methods=['POST'])
def salida_manual():
    data = request.json or {}
    placa = data.get('placa', '').upper().strip()

    if not placa:
        # Buscar cualquier vehiculo para sacar
        vehiculos = obtener_vehiculos_estacionados()
        if not vehiculos:
            return jsonify({"exito": False, "mensaje": "No hay vehiculos para retirar."})
        placa = random.choice(vehiculos)["placa"]

    espacio = liberar_vehiculo(placa)
    if espacio:
        camara_lpr["ultima_placa_detectada"] = placa
        camara_lpr["ultimo_estado"] = "salida"
        camara_lpr["ultima_deteccion"] = datetime.now().strftime("%H:%M:%S")
        registrar_evento("salida",
            f"SALIDA - {placa} libero el espacio {espacio['id']}",
            placa=placa,
            detalle={"espacio": espacio["id"]})
        return jsonify({"exito": True, "espacio_liberado": espacio})
    else:
        return jsonify({"exito": False, "mensaje": "Vehiculo no encontrado."})


if __name__ == '__main__':
    init_db()
    print("=" * 50)
    print("  PARQUEO INTELIGENTE UPB - SIMULADOR")
    print("  Sistema LPR con camaras y control de acceso")
    print("=" * 50)
    print(f"  Placas autorizadas: {len(PLACAS_AUTORIZADAS)}")
    print(f"  Espacios totales: 32 (4 zonas x 8)")
    print(f"  Servidor: http://localhost:5000")
    print("=" * 50)
    app.run(debug=True, port=5000, threaded=True)
