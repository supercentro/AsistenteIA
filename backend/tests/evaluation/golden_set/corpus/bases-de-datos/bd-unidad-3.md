Las bases de datos documentales guardan registros flexibles, normalmente en formato JSON, sin exigir un esquema fijo. Resultan cómodas cuando la estructura cambia con frecuencia, aunque ofrecen menos garantías para las consultas con muchas relaciones.

El teorema CAP afirma que un sistema distribuido no puede garantizar a la vez consistencia, disponibilidad y tolerancia a particiones de red. Ante una partición hay que elegir entre responder con datos posiblemente antiguos o rechazar la petición.

Una vista es una consulta guardada con nombre que se usa como si fuera una tabla. Sirve para simplificar consultas complejas y para ocultar columnas sensibles a ciertos usuarios sin duplicar los datos.

Un disparador o trigger es código que la base ejecuta automáticamente antes o después de una inserción, actualización o borrado. Se usa para auditar cambios o mantener valores derivados, aunque abusar de ellos dificulta entender el comportamiento.

El registro de escritura anticipada guarda cada cambio en un fichero secuencial antes de aplicarlo a los datos. Tras una caída se reproduce ese registro para recuperar el estado, y también permite restaurar la base a un instante concreto.
