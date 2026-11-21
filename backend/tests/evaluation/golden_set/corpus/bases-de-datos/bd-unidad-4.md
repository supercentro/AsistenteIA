La desnormalización duplica deliberadamente información para evitar uniones costosas y acelerar las lecturas. El precio es mayor espacio y el riesgo de inconsistencias si las copias no se actualizan juntas.

El particionado divide una tabla enorme en trozos más pequeños según un criterio, por ejemplo la fecha. Las consultas que filtran por ese criterio solo leen las particiones necesarias, y el mantenimiento se puede hacer partición a partición.

En la replicación una copia principal envía sus cambios a una o más réplicas. Las réplicas reparten las lecturas y sirven de reserva si la principal falla, aunque con replicación asíncrona pueden ir ligeramente por detrás.

La inyección de SQL ocurre cuando una aplicación construye consultas concatenando texto del usuario, que puede alterar la sentencia. Se previene con consultas parametrizadas, que envían los valores separados del código SQL.

El optimizador elige el plan de ejecución más barato según las estadísticas de las tablas. El comando EXPLAIN muestra ese plan, indica si se usan índices o recorridos completos y ayuda a descubrir por qué una consulta es lenta.
