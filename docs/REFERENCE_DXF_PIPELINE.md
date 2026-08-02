# Dataset-driven DXF pipeline

Заводские DXF — эталонная геометрия, а не размеченный датасет для нейросети. Pipeline извлекает замкнутые контуры из `LINE`, `ARC`, `CIRCLE`, `LWPOLYLINE`, `POLYLINE`, `SPLINE`, `ELLIPSE`, поэтому покрывает произвольные комбинации прямых и кривых.

## Установка

```bash
pip install -r requirements-reference.txt
```

## Аудит датасета

```bash
PYTHONPATH=src python src/analyze_reference_dataset.py dataset/reference_shapes
```

## Два выходных файла

```bash
PYTHONPATH=src python src/reference_dxf_pipeline.py 'dataset/reference_shapes/011(10).dxf' output/011
```

Создаются `output/011_CNC.dxf`, `output/011_DIMENSIONED.dxf` и `output/011_manifest.json`. Для смешанных чертежей указывайте производственные слои: `--layers стекло,CUT`. Кривые преобразуются с допуском `--flatten 0.05` мм. Перед резкой оператор обязан проверить контуры; `safe_for_cnc` намеренно остаётся `false`.
