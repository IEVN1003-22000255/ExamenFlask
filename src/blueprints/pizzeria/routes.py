from flask import Blueprint, jsonify, request, current_app
from database import mysql

pizzeria_bp = Blueprint('pizzeria', __name__, url_prefix='/api/pizzeria')

PRECIOS_TAMANO = {'Chica': 40, 'Mediana': 80, 'Grande': 120}
PRECIOS_INGREDIENTE = 10

def calcular_subtotal(tamano, ingredientes, num_pizzas):
    precio_base = PRECIOS_TAMANO.get(tamano, 0)
    costo_ingredientes = len(ingredientes) * PRECIOS_INGREDIENTE
    return (precio_base + costo_ingredientes) * num_pizzas

@pizzeria_bp.route("/", methods=["GET"])
def listar_pedidos():
    cursor = None
    try:
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT id, nombre, direccion, telefono, total, fecha FROM p_pedidos ORDER BY id DESC")
        filas = cursor.fetchall()
        
        pedidos = []
        for f in filas:
            pedido_id = f[0]
            cursor.execute("SELECT tamano, ingredientes, num_pizzas, subtotal FROM p_detalle_pedidos WHERE pedido_id = %s", (pedido_id,))
            detalles_db = cursor.fetchall()
            detalles = []
            for d in detalles_db:
                detalles.append({
                    "tamano": d[0],
                    "ingredientes": d[1].split(', ') if d[1] else [],
                    "numPizzas": d[2],
                    "subtotal": float(d[3])
                })
            
            pedidos.append({
                "id": pedido_id,
                "nombre": f[1],
                "direccion": f[2],
                "telefono": f[3],
                "total": float(f[4]),
                "fecha": f[5].isoformat() if f[5] else None,
                "detalles": detalles
            })
            
        return jsonify({"pedidos": pedidos, "exito": True}), 200
    except Exception as ex:
        current_app.logger.error("Error al consultar pedidos: %s", ex)
        return jsonify({"mensaje": "Error al consultar los pedidos", "exito": False}), 500
    finally:
        if cursor: cursor.close()

@pizzeria_bp.route("/", methods=["POST"])
def registrar_pedido():
    datos = request.get_json(silent=True)
    if not datos:
        return jsonify({"mensaje": "Se requiere un objeto JSON", "exito": False}), 400
    
    nombre = str(datos.get("nombre", "")).strip()
    direccion = str(datos.get("direccion", "")).strip()
    telefono = str(datos.get("telefono", "")).strip()
    fecha = datos.get("fecha")
    detalles = datos.get("detalles", [])
    
    if not nombre or not direccion or not telefono or not detalles:
        return jsonify({"mensaje": "Faltan datos del cliente o no hay pizzas agregadas", "exito": False}), 400
    
    total_pedido = 0
    calculos = []
    for item in detalles:
        tamano = item.get("tamano")
        ingredientes = item.get("ingredientes", [])
        try:
            num_pizzas = int(item.get("numPizzas"))
        except (TypeError, ValueError):
            return jsonify({"mensaje": "Número de pizzas inválido", "exito": False}), 400
        
        subtotal = calcular_subtotal(tamano, ingredientes, num_pizzas)
        total_pedido += subtotal
        calculos.append((tamano, ", ".join(ingredientes), num_pizzas, subtotal))
        
    cursor = None
    try:
        cursor = mysql.connection.cursor()
        if fecha:
            cursor.execute("""
                INSERT INTO p_pedidos (nombre, direccion, telefono, total, fecha)
                VALUES (%s, %s, %s, %s, %s)
            """, (nombre, direccion, telefono, total_pedido, fecha))
        else:
            cursor.execute("""
                INSERT INTO p_pedidos (nombre, direccion, telefono, total)
                VALUES (%s, %s, %s, %s)
            """, (nombre, direccion, telefono, total_pedido))
        
        pedido_id = cursor.lastrowid
        
        for calc in calculos:
            cursor.execute("""
                INSERT INTO p_detalle_pedidos (pedido_id, tamano, ingredientes, num_pizzas, subtotal)
                VALUES (%s, %s, %s, %s, %s)
            """, (pedido_id, calc[0], calc[1], calc[2], calc[3]))
            
        mysql.connection.commit()
        return jsonify({"mensaje": "Pedido registrado correctamente", "id": pedido_id, "total": total_pedido, "exito": True}), 201
    except Exception as ex:
        mysql.connection.rollback()
        current_app.logger.error("Error al registrar pedido: %s", ex)
        return jsonify({"mensaje": "Error al registrar el pedido", "exito": False}), 500
    finally:
        if cursor: cursor.close()

@pizzeria_bp.route("/<int:id>", methods=["PUT"])
def modificar_pedido(id):
    datos = request.get_json(silent=True)
    if not datos:
        return jsonify({"mensaje": "Se requiere un objeto JSON", "exito": False}), 400

    nombre = str(datos.get("nombre", "")).strip()
    direccion = str(datos.get("direccion", "")).strip()
    telefono = str(datos.get("telefono", "")).strip()

    cursor = None
    try:
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT id FROM p_pedidos WHERE id = %s", (id,))
        if cursor.fetchone() is None:
            return jsonify({"mensaje": "No existe un pedido con ese ID", "exito": False}), 404

        cursor.execute("""
            UPDATE p_pedidos
            SET nombre = %s, direccion = %s, telefono = %s
            WHERE id = %s
        """, (nombre, direccion, telefono, id))
        mysql.connection.commit()

        return jsonify({"mensaje": "Pedido modificado correctamente", "exito": True}), 200
    except Exception as ex:
        mysql.connection.rollback()
        current_app.logger.error("Error al modificar pedido: %s", ex)
        return jsonify({"mensaje": "Error al modificar el pedido", "exito": False}), 500
    finally:
        if cursor: cursor.close()

@pizzeria_bp.route("/<int:id>", methods=["DELETE"])
def eliminar_pedido(id):
    cursor = None
    try:
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT id FROM p_pedidos WHERE id = %s", (id,))
        if cursor.fetchone() is None:
            return jsonify({"mensaje": "No existe un pedido con ese ID", "exito": False}), 404

        cursor.execute("DELETE FROM p_pedidos WHERE id = %s", (id,))
        mysql.connection.commit()

        return jsonify({"mensaje": "Pedido eliminado con éxito", "exito": True}), 200
    except Exception as ex:
        mysql.connection.rollback()
        current_app.logger.error("Error al eliminar pedido: %s", ex)
        return jsonify({"mensaje": "Error al eliminar el pedido", "exito": False}), 500
    finally:
        if cursor: cursor.close()

@pizzeria_bp.route("/ventas/dia/<string:fecha>", methods=["GET"])
def ventas_por_dia(fecha):
    cursor = None
    try:
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT nombre, total FROM p_pedidos WHERE fecha = %s", (fecha,))
        filas = cursor.fetchall()
        ventas = [{"nombre": f[0], "total": float(f[1])} for f in filas]
        total_dia = sum(v["total"] for v in ventas)
        return jsonify({"ventas": ventas, "total_dia": total_dia, "exito": True}), 200
    except Exception as ex:
        current_app.logger.error("Error al consultar ventas por día: %s", ex)
        return jsonify({"mensaje": "Error al consultar ventas", "exito": False}), 500
    finally:
        if cursor: cursor.close()