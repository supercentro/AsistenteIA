Una combinación INNER JOIN devuelve solo las filas que tienen correspondencia en ambas tablas, mientras que LEFT JOIN conserva todas las filas de la tabla izquierda y rellena con valores nulos cuando no hay pareja a la derecha.

Un índice de árbol B acelera las búsquedas por igualdad y por rango porque mantiene los valores ordenados. A cambio ocupa espacio y ralentiza ligeramente las inserciones y actualizaciones, que deben mantenerlo al día.

Las transacciones cumplen las propiedades ACID: atomicidad, consistencia, aislamiento y durabilidad. O se aplican todas las operaciones o ninguna, y una vez confirmada una transacción sus cambios sobreviven a un fallo del sistema.

Los niveles de aislamiento determinan qué anomalías pueden ver las transacciones concurrentes: lecturas sucias, lecturas no repetibles y fantasmas. Cuanto más estricto es el nivel, menos concurrencia se obtiene.

Un interbloqueo ocurre cuando dos transacciones esperan cada una un bloqueo que tiene la otra y ninguna puede avanzar. El gestor lo detecta, aborta una de ellas y permite que la otra continúe.
