# ProyectoPuntajePython

## Clasificación y marcadores por set

Los resultados guardados en `main.py` mantienen el puntaje tradicional del
partido (3/0, 2/1, 1/2 o 0/3) y además conservan los marcadores reales de cada
set en `score_lines`. La clasificación calcula desde esos resultados:

- **PF (puntos a favor):** suma de los puntos anotados por el equipo en todos
  los sets confirmados.
- **PC (puntos en contra):** suma de los puntos anotados por el rival en esos
  mismos sets.

El orden es: puntos por resultados tradicionales (descendente), PF
(descendente) y PC (ascendente). Si continúa el empate, se conserva el orden
estable de carga existente. Los resultados históricos que no contienen
marcadores reales mantienen sus puntos tradicionales, pero muestran PF y PC en
0 para evitar inventar datos.

La edición y eliminación recalculan la tabla directamente desde los resultados
persistidos, evitando dobles conteos. El guardado atómico y las copias de
seguridad existentes de `DataStore` siguen siendo el mecanismo de persistencia.

Para ejecutar las pruebas integradas:

```bash
python3 main.py --test
```
