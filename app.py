import streamlit as st
import folium
from streamlit_folium import folium_static
import simplekml
import random
import math
import fastkml
from pygeoif import geometry
from shapely.geometry import Polygon, Point
from collections import deque
import numpy as np

# Inicialización de la página
st.set_page_config(page_title="Acomodar Patrón de Siembra en KML", layout="wide")

# Título de la aplicación
st.title("Acomodar Patrón de Siembra en Polígonos KML con Imágenes Satelitales")

# Cargar un archivo KML para definir los polígonos
uploaded_kml = st.file_uploader("Subir archivo KML con los polígonos", type=["kml"])

# Definición de especies con íconos personalizados y colores
especies = {
    'Z': {'nombre': 'Zapote Mamey', 'color': 'red', 'icono': 'http://maps.google.com/mapfiles/kml/paddle/red-circle.png'},
    'L': {'nombre': 'Litchi', 'color': 'green', 'icono': 'http://maps.google.com/mapfiles/kml/paddle/grn-circle.png'},
    'M': {'nombre': 'Mango Tommy', 'color': 'yellow', 'icono': 'http://maps.google.com/mapfiles/kml/paddle/ylw-circle.png'},
    'R': {'nombre': 'Rambután', 'color': 'blue', 'icono': 'http://maps.google.com/mapfiles/kml/paddle/blu-circle.png'},
    'G': {'nombre': 'Guayaba Rosa', 'color': 'purple', 'icono': 'http://maps.google.com/mapfiles/kml/paddle/purple-circle.png'},
    'N': {'nombre': 'Naranjas de Mesa', 'color': 'orange', 'icono': 'http://maps.google.com/mapfiles/kml/paddle/orange-circle.png'},
    'S': {'nombre': 'Limón', 'color': 'white', 'icono': 'http://maps.google.com/mapfiles/kml/paddle/wht-circle.png'},
    'J': {'nombre': 'Jaboticabo', 'color': 'pink', 'icono': 'http://maps.google.com/mapfiles/kml/paddle/pink-circle.png'}  # Color para Jaboticabo
}

# Normalizar los porcentajes para que sumen 100%
def normalizar_porcentajes(porcentajes):
    total = sum(porcentajes.values())
    for key in porcentajes:
        porcentajes[key] = (porcentajes[key] / total) * 100
    return porcentajes

# Función para generar rangos fraccionarios (como range pero con floats)
def frange(start, stop, step):
    while start < stop:
        yield start
        start += step

# Función para mezclar especies minimizando adyacencias
def mezclar_especies_minimizando_adyacentes(lista_especies, grid_size):
    # Crear una matriz vacía para colocar las especies
    grid = np.full(grid_size, None)
    posiciones = [(i, j) for i in range(grid_size[0]) for j in range(grid_size[1])]
    random.shuffle(posiciones)

    # Colocar cada especie tratando de minimizar vecinos adyacentes de la misma especie
    for especie in lista_especies:
        mejor_posicion = None
        menor_vecinos = float('inf')
        for pos in posiciones:
            if grid[pos] is None:
                vecinos = contar_vecinos(grid, pos, especie)
                if vecinos < menor_vecinos:
                    menor_vecinos = vecinos
                    mejor_posicion = pos
                    # Si encontramos una posición sin vecinos iguales, podemos detenernos
                    if vecinos == 0:
                        break
        # Colocar la especie en la mejor posición encontrada
        if mejor_posicion is not None:
            grid[mejor_posicion] = especie
            if mejor_posicion in posiciones:
                posiciones.remove(mejor_posicion)

    # Convertir la matriz en una lista de especies
    lista_resultante = [grid[i, j] for i in range(grid_size[0]) for j in range(grid_size[1]) if grid[i, j] is not None]
    return lista_resultante

# Función para contar los vecinos adyacentes de la misma especie
def contar_vecinos(grid, pos, especie):
    vecinos = 0
    filas, columnas = grid.shape
    for i in range(max(0, pos[0] - 1), min(filas, pos[0] + 2)):
        for j in range(max(0, pos[1] - 1), min(columnas, pos[1] + 2)):
            if (i, j) != pos and grid[i, j] == especie:
                vecinos += 1
    return vecinos

# Función para mezclar especies aleatoriamente
def mezclar_especies_aleatoriamente(lista_especies):
    random.shuffle(lista_especies)
    return lista_especies

# Función para crear varias opciones de mezcla
def generar_mezclas(lista_especies, num_opciones=3):
    opciones = []
    for _ in range(num_opciones):
        mezcla = lista_especies.copy()
        random.shuffle(mezcla)
        opciones.append(mezcla)
    return opciones

# Ajuste de tolerancia para los puntos en los bordes
tolerancia = 0.00001  # Pequeña tolerancia para considerar puntos en los bordes del polígono

# Función para generar el patrón de árboles dentro del polígono
def generar_patron_dentro_poligono(poligono, delta_lat, delta_lon, lista_especies):
    arboles = []
    bounds = poligono.bounds  # Obtener los límites del polígono
    index = 0

    # Aumentamos el paso para cubrir más área
    delta_lat *= 1.1  # Aumentamos el paso para mejorar la cobertura
    delta_lon *= 1.1  # Aumentamos el paso para mejorar la cobertura

    # Iterar sobre la grilla dentro del polígono
    for lat in frange(bounds[1] - tolerancia, bounds[3] + tolerancia, delta_lat):  # from min_lat to max_lat
        for lon in frange(bounds[0] - tolerancia, bounds[2] + tolerancia, delta_lon):  # from min_lon to max_lon
            punto = Point(lon, lat)
            if poligono.contains(punto) or poligono.touches(punto):  # Considerar puntos que tocan el borde
                if index < len(lista_especies):
                    especie = lista_especies[index]
                    arboles.append((lat, lon, especie))
                    index += 1
    return arboles

# Si se sube un archivo KML, procesarlo
if uploaded_kml is not None:
    st.write("Archivo KML cargado. Procesando...")  # Mensaje para confirmar la carga
    # Leer el archivo KML como bytes sin decodificar manualmente
    kml = fastkml.KML()

    kml_bytes = uploaded_kml.read()  # Leer archivo como bytes

    try:
        kml.from_string(kml_bytes)  # Procesar los bytes directamente
        st.write("Archivo KML procesado correctamente.")
    except Exception as e:
        st.error(f"Error al procesar el archivo KML: {e}")

    # Extraer los polígonos recursivamente
    def buscar_poligonos(features):
        polygon_list = []
        for feature in features:
            if isinstance(feature, fastkml.kml.Document) or isinstance(feature, fastkml.kml.Folder):
                polygon_list.extend(buscar_poligonos(feature.features()))  # Llamada recursiva si es Document o Folder
            elif isinstance(feature, fastkml.kml.Placemark) and isinstance(feature.geometry, geometry.Polygon):
                # Convertir el polígono de pygeoif a shapely
                coords = list(feature.geometry.exterior.coords)
                shapely_polygon = Polygon(coords)
                polygon_list.append(shapely_polygon)
        return polygon_list

    polygon_list = buscar_poligonos(kml.features())

    if polygon_list:
        st.success(f"Se encontraron {len(polygon_list)} polígonos en el archivo KML.")

        # Ajuste de la distancia entre árboles
        distancia = st.slider("Distancia entre árboles (metros)", min_value=3, max_value=15, value=6)

        # Conversión de metros a grados
        delta_lat = distancia / 111320
        delta_lon = delta_lat  # Para evitar deformaciones, mantendremos la relación entre latitud y longitud

        # Calcular la cantidad máxima de árboles que caben en el polígono
        def calcular_arboles_maximos(poligono, delta_lat, delta_lon):
            count = 0
            bounds = poligono.bounds
            for lat in frange(bounds[1], bounds[3], delta_lat):
                for lon in frange(bounds[0], bounds[2], delta_lon):
                    punto = Point(lon, lat)
                    if poligono.contains(punto):
                        count += 1
            return count

        total_arboles_poligono = sum(calcular_arboles_maximos(poligono, delta_lat, delta_lon) for poligono in polygon_list)
        st.write(f"Cantidad máxima de árboles que caben en los polígonos: {total_arboles_poligono}")

        # Mostrar los porcentajes iniciales ajustados
        st.write("Porcentajes de cada especie (ajustables):")
        porcentajes = {}
        for key, especie in especies.items():
            nuevo_valor = st.slider(f"{especie['nombre']}", min_value=0, max_value=100, value=int(100 / len(especies)))
            porcentajes[key] = nuevo_valor

        # Validación para asegurar que los porcentajes sumen 100%
        total_porcentajes = sum(porcentajes.values())
        if total_porcentajes != 100:
            st.error(f"Los porcentajes de los árboles deben sumar 100%. Actualmente suman: {total_porcentajes}%")
        else:
            # Normalización automática de los porcentajes para que sumen 100%
            porcentajes = normalizar_porcentajes(porcentajes)

            # Generar la lista de especies basada en los porcentajes y el total de árboles que caben
            lista_especies = []
            for key, porcentaje in porcentajes.items():
                cantidad = int((porcentaje / 100) * total_arboles_poligono)
                lista_especies.extend([key] * cantidad)

            # Generar tres opciones de mezcla aleatoria
            mezclas = generar_mezclas(lista_especies, num_opciones=3)

            # Selección de la opción de mezcla
            opcion_seleccionada = st.selectbox("Selecciona una mezcla de especies", ["Opción 1", "Opción 2", "Opción 3"])

            # Dependiendo de la selección, obtener la mezcla correspondiente
            if opcion_seleccionada == "Opción 1":
                lista_especies = mezclas[0]
            elif opcion_seleccionada == "Opción 2":
                lista_especies = mezclas[1]
            else:
                lista_especies = mezclas[2]

            # Definir el tamaño de la cuadrícula para la distribución de árboles
            grid_size = (int(math.sqrt(total_arboles_poligono)),) * 2

            # Mezclar especies minimizando adyacencias
            lista_especies = mezclar_especies_minimizando_adyacentes(lista_especies, grid_size)

            # Generar los árboles para cada polígono
            all_arboles = []
            conteo_especies = {key: 0 for key in especies.keys()}  # Inicializar conteo de cada especie
            for poligono in polygon_list:
                arboles_poligono = generar_patron_dentro_poligono(poligono, delta_lat, delta_lon, lista_especies)
                all_arboles.extend(arboles_poligono)
                for _, _, especie in arboles_poligono:
                    conteo_especies[especie] += 1

            # Mostrar el conteo de árboles por especie
            st.write("Conteo de árboles dentro del polígono por especie:")
            for key, count in conteo_especies.items():
                st.write(f"{especies[key]['nombre']}: {count} árboles")

            # Mostrar el mapa con los puntos de los árboles y los polígonos
            st.subheader("Mapa de los árboles y los polígonos (Vista Satelital):")

            # Extraemos latitud y longitud del centroid de la geometría del primer polígono (shapely centroid)
            centroid_lat = polygon_list[0].centroid.y
            centroid_lon = polygon_list[0].centroid.x

            # Crear el mapa satelital con la ubicación del primer polígono
            mapa = folium.Map(location=[centroid_lat, centroid_lon], zoom_start=16, width='100%', height='700px')

            # Añadir capa satelital similar a Google Earth con la atribución requerida
            folium.TileLayer(
                tiles='https://{s}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
                attr='Map data © Google',
                name='Google Satellite',
                max_zoom=20,
                subdomains=['mt0', 'mt1', 'mt2', 'mt3']
            ).add_to(mapa)

            # Añadir los polígonos al mapa
            for poligono in polygon_list:
                folium.Polygon(
                    locations=[(lat, lon) for lon, lat, *_ in poligono.exterior.coords[:]],  # Desempaquetar solo lat y lon
                    color='blue',
                    weight=2,
                    fill=True,
                    fill_opacity=0.2
                ).add_to(mapa)

            # Añadir cada árbol al mapa con su color
            for arbol in all_arboles:
                especie = especies[arbol[2]]
                folium.Marker(
                    location=[arbol[0], arbol[1]],  # Latitud y Longitud separadas
                    icon=folium.Icon(icon='info-sign', color=especie['color']),
                    popup=especie['nombre']
                ).add_to(mapa)

            # Añadir clave de colores al mapa
            legend_html = '''
            <div style="position: fixed; 
                        bottom: 50px; left: 50px; width: 300px; height: 300px; 
                        background-color: white; z-index:9999; font-size:14px;
                        border:2px solid grey; padding: 10px;">
                <b>Clave de Colores:</b><br>
                <i class="fa fa-map-marker" style="color:red"></i> Zapote Mamey<br>
                <i class="fa fa-map-marker" style="color:green"></i> Litchi<br>
                <i class="fa fa-map-marker" style="color:yellow"></i> Mango Tommy<br>
                <i class="fa fa-map-marker" style="color:blue"></i> Rambután<br>
                <i class="fa fa-map-marker" style="color:purple"></i> Guayaba Rosa<br>
                <i class="fa fa-map-marker" style="color:orange"></i> Naranjas de Mesa<br>
                <i class="fa fa-map-marker" style="color:white"></i> Limón<br>
                <i class="fa fa-map-marker" style="color:pink"></i> Jaboticabo<br>
            </div>
            '''
            mapa.get_root().html.add_child(folium.Element(legend_html))

            # Mostrar el mapa en la aplicación
            folium.LayerControl().add_to(mapa)
            folium_static(mapa)

            # Descargar archivo KML con íconos personalizados
            def descargar_kml(arboles):
                kml = simplekml.Kml()
                for arbol in arboles:
                    especie = especies[arbol[2]]
                    pnt = kml.newpoint(name=especie['nombre'], coords=[(arbol[1], arbol[0])])
                    pnt.style.iconstyle.icon.href = especie['icono']  # Ícono personalizado
                    pnt.style.iconstyle.scale = 1.1  # Escala del ícono en Google Earth
                return kml

            # Botón para generar y descargar el archivo KML
            if st.button("Descargar KML"):
                kml = descargar_kml(all_arboles)
                kml.save("patron_siembra.kml")
                st.success("Archivo KML generado. Descárgalo aquí:")
                st.download_button("Descargar KML", data=open("patron_siembra.kml", "rb").read(), file_name="patron_siembra.kml")
    else:
        st.warning("No se encontraron polígonos en el archivo KML.")
