# Operator sketch workflow

Цель: фото эскиза → выбор заводской топологии → подтверждение всех размеров → два DXF.

```bash
PYTHONPATH=src python src/sketch_shape_matcher.py index dataset/reference_shapes dataset/shape_index.json
PYTHONPATH=src python src/operator_workflow.py create photo.jpg dataset/shape_index.json output/job.json
```

Оператор выбирает `selected_reference`, заполняет размеры с `target` (`outer.width`, `hole_1.diameter`, `slot_1.depth`) и подтверждает геометрию. Неоднозначное OCR-значение автоматически не принимается; экспорт блокируется, пока хотя бы один размер не подтверждён.

```bash
PYTHONPATH=src python src/operator_workflow.py export output/job.json dataset/reference_shapes output/order_001
```

Текущая фаза выбирает и очищает заводскую топологию. Для перестроения каждого локального радиуса и паза по новым значениям эталонам нужны параметрические схемы (`target` для каждого размера). Схемы формируются автоматически насколько возможно и затем один раз подтверждаются человеком.
