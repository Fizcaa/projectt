import sys, sqlite3, hashlib
from pathlib import Path

db = sqlite3.connect("file_index.db")
db.row_factory = sqlite3.Row
db.execute("CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, size INT, hash TEXT, mtime REAL)")


def get_hash(p):
    try:
        return hashlib.md5(p.read_bytes()).hexdigest()
    except OSError:
        return None


def scan(d):
    print(f"\n[*] Сканирование директории: {d}")
    root = Path(d).resolve()
    if not root.exists(): return print("[-] Ошибка: Указанный путь не существует.")

    db_files = {r['path']: r['mtime'] for r in
                db.execute("SELECT path, mtime FROM files WHERE path LIKE ?", (f"{root}%",))}
    scanned = set()
    added, updated = 0, 0

    for p in (x for x in root.rglob('*') if x.is_file()):
        abs_path = str(p)
        scanned.add(abs_path)
        try:
            mtime, size = p.stat().st_mtime, p.stat().st_size
        except OSError:
            continue

        if abs_path not in db_files:
            db.execute("INSERT OR REPLACE INTO files VALUES (?, ?, ?, ?)", (abs_path, size, get_hash(p), mtime))
            added += 1
        elif db_files[abs_path] != mtime:
            db.execute("INSERT OR REPLACE INTO files VALUES (?, ?, ?, ?)", (abs_path, size, get_hash(p), mtime))
            updated += 1

    deleted = set(db_files) - scanned
    for p in deleted: db.execute("DELETE FROM files WHERE path = ?", (p,))
    db.commit()

    print("[+] Сканирование завершено!")
    print(f"    Добавлено новых файлов: {added}")
    print(f"    Обновлено изменившихся: {updated}")
    print(f"    Удалено из индекса: {len(deleted)}")


def dups():
    print("\n[*] Поиск дубликатов...")
    q = "SELECT size, hash, GROUP_CONCAT(path, '\n    -> ') as paths FROM files WHERE hash IS NOT NULL GROUP BY hash HAVING COUNT(*)>1"
    res = db.execute(q).fetchall()

    if not res: return print("[+] Дубликаты не найдены.")
    for r in res:
        print(f"\n[!] Дубликат найден (Размер: {r['size']} байт, Хеш: {r['hash']}):\n    -> {r['paths']}")


def verify(src, bak):
    print(f"\n[*] Проверка резервной копии...\n    Источник: {src}\n    Бэкап:    {bak}")
    scan(src);
    scan(bak)

    s_root, b_root = Path(src).resolve(), Path(bak).resolve()
    bak_db = {r['path']: (r['hash'], r['size']) for r in
              db.execute("SELECT path, hash, size FROM files WHERE path LIKE ?", (f"{b_root}%",))}
    errs = 0

    for r in db.execute("SELECT path, hash, size FROM files WHERE path LIKE ?", (f"{s_root}%",)):
        rel_path = str(Path(r['path']).relative_to(s_root))
        exp_bak = str(b_root / rel_path)

        b_file = bak_db.get(exp_bak)
        if not b_file:
            print(f"[-] Отсутствует в бэкапе: {rel_path}");
            errs += 1
        elif b_file[0] != r['hash'] or b_file[1] != r['size']:
            print(f"[-] Файл поврежден или не совпадает в бэкапе: {rel_path}");
            errs += 1

    if errs == 0:
        print("\n[+] Успех! Резервная копия полностью идентична источнику.")
    else:
        print(f"\n[!] Проверка завершена с ошибками. Проблемных файлов: {errs}")


def print_help():
    print(
        "\nИспользование:\n  python script.py scan <путь_к_папке>\n  python script.py duplicates\n  python script.py verify <источник> <бэкап>")


if __name__ == "__main__":
    args = sys.argv[1:]
    cmd = args[0].lower() if args else ""

    if cmd == "scan" and len(args) == 2:
        scan(args[1])
    elif cmd in ("duplicates", "dups"):
        dups()
    elif cmd == "verify" and len(args) == 3:
        verify(args[1], args[2])
    else:
        print_help()