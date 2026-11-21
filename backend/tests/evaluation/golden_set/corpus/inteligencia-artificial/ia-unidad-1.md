En el aprendizaje supervisado el algoritmo recibe ejemplos etiquetados, es decir, pares formados por una entrada y la salida esperada, y ajusta sus parámetros para predecir la etiqueta de datos nuevos. Clasificar correos como spam o no spam es un caso típico.

El aprendizaje no supervisado trabaja con datos sin etiquetar y busca estructura oculta en ellos. El agrupamiento o clustering reúne observaciones parecidas, y la reducción de dimensionalidad resume muchas variables en pocas componentes.

Hay sobreajuste cuando un modelo memoriza el ruido del conjunto de entrenamiento y deja de generalizar. Se detecta porque el error en entrenamiento es muy bajo mientras que el error en datos de prueba es alto. La regularización y más datos ayudan a evitarlo.

La validación cruzada divide los datos en k partes: en cada ronda se entrena con k menos una de ellas y se evalúa con la restante. Promediar los resultados da una estimación más estable del rendimiento que una única partición.

Una neurona artificial suma sus entradas multiplicadas por pesos, añade un sesgo y aplica una función de activación como la sigmoide o la ReLU. Al apilar capas de neuronas se obtiene una red capaz de aproximar funciones muy complejas.
