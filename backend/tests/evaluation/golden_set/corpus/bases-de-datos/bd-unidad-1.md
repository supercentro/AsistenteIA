El modelo relacional organiza los datos en tablas formadas por filas y columnas. Cada tabla representa una entidad y las relaciones entre entidades se expresan mediante valores comunes y no mediante punteros físicos.

La clave primaria identifica de forma única cada fila de una tabla, no puede ser nula y no puede repetirse. Puede estar formada por una sola columna o por varias, en cuyo caso se llama clave compuesta.

Una clave foránea es una columna que referencia la clave primaria de otra tabla y garantiza la integridad referencial. Con borrado en cascada, al eliminar la fila principal se eliminan también las filas que dependen de ella.

La normalización reduce la redundancia descomponiendo las tablas. En primera forma normal cada celda guarda un valor atómico, en segunda no hay dependencias parciales de la clave y en tercera no hay dependencias entre atributos que no son clave.

La sentencia SELECT consulta datos de una o varias tablas. La cláusula WHERE filtra filas, GROUP BY agrupa, HAVING filtra grupos y ORDER BY ordena el resultado final.
