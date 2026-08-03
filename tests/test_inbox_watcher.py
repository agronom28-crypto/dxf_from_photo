from inbox_watcher import InboxWatcher, INBOX_NAME, OUTPUT_NAME

def fake_processor(source,work):
    clear=work/"part_CNC.dxf"; info=work/"part_DIMENSIONED.dxf"; clear.write_text("CLEAR"); info.write_text("INFO"); return [clear,info]
def test_startup_creates_russian_folders(tmp_path):
    InboxWatcher(tmp_path,processor=fake_processor)
    assert (tmp_path/INBOX_NAME).is_dir() and (tmp_path/OUTPUT_NAME).is_dir()
def test_image_creates_two_named_outputs(tmp_path):
    watcher=InboxWatcher(tmp_path,processor=fake_processor); source=tmp_path/INBOX_NAME/"заказ 15.jpg"; source.write_bytes(b"image"); assert watcher.scan(force_stable=True)==1
    assert (tmp_path/OUTPUT_NAME/"заказ 15_dxf_clear.dxf").read_text()=="CLEAR"; assert (tmp_path/OUTPUT_NAME/"заказ 15_dxf_info.dxf").read_text()=="INFO"
def test_unchanged_file_is_not_processed_twice(tmp_path):
    calls=[]
    def processor(source,work): calls.append(source); return fake_processor(source,work)
    watcher=InboxWatcher(tmp_path,processor=processor); source=tmp_path/INBOX_NAME/"a.png"; source.write_bytes(b"x"); watcher.scan(force_stable=True); watcher.scan(force_stable=True); assert len(calls)==1
def test_unsupported_file_is_ignored(tmp_path):
    watcher=InboxWatcher(tmp_path,processor=fake_processor); (tmp_path/INBOX_NAME/"notes.txt").write_text("x"); assert watcher.scan(force_stable=True)==0
