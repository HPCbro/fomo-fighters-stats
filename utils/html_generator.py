# /root/ff/utils/html_generator.py
import pandas as pd
import os
import subprocess
from datetime import timedelta, datetime

OUTPUT_FILENAME = 'index.html' # Для GitHub Pages нужен именно index.html

def format_time(seconds):
    if not seconds: return ""
    return str(timedelta(seconds=int(seconds)))

def pretty_requirements(req_dict, trans_map={}):
    if not isinstance(req_dict, dict): return ""
    parts = []
    for k, v in req_dict.items():
        name = trans_map.get(k, k)
        parts.append(f"{name}: {v}")
    return ", ".join(parts)

def build_translation_map(data):
    mapping = {}
    scan_keys = ['dbBuildings', 'dbSkills', 'dbTroops', 'dbRes', 'dbRaces']
    for k in scan_keys:
        if k in data and isinstance(data[k], list):
            for item in data[k]:
                if isinstance(item, dict) and 'key' in item and 'title' in item:
                    mapping[item['key']] = item['title']
    return mapping

# --- Обработчики ---

def process_nested(data_list, trans_map):
    rows = []
    for item in data_list:
        base = {k: v for k, v in item.items() if k != 'levels'}
        if 'levels' in item and isinstance(item['levels'], list):
            for lvl in item['levels']:
                row = base.copy()
                row.update(lvl)
                if 'requiredBuildings' in row:
                    row['requiredBuildings'] = pretty_requirements(row['requiredBuildings'], trans_map)
                if 'requiredSkills' in row:
                    row['requiredSkills'] = pretty_requirements(row['requiredSkills'], trans_map)
                if 'time' in row:
                    row['time_formatted'] = format_time(row['time'])
                rows.append(row)
        else:
            rows.append(base)
    return pd.DataFrame(rows)

def process_parallel(data_list):
    rows = []
    for q in data_list:
        base = {k: v for k, v in q.items() if not isinstance(v, list)}
        arrays = {k: v for k, v in q.items() if isinstance(v, list) and v}
        if not arrays:
            rows.append(base)
            continue
        max_len = max(len(x) for x in arrays.values())
        for i in range(max_len):
            row = base.copy()
            row['Level/Step'] = i + 1
            for k, arr in arrays.items():
                row[k] = arr[i] if i < len(arr) else None
            rows.append(row)
    return pd.DataFrame(rows)

def process_simple(data_list, trans_map):
    df = pd.json_normalize(data_list)
    if 'building' in df.columns:
        df['building_name'] = df['building'].map(lambda x: trans_map.get(x, x))
    return df

def generate_html_content(data_frames):
    nav_buttons = ""
    tables_html = ""
    
    # Стили и скрипты (Темная тема)
    head = """
    <head>
        <meta charset="UTF-8">
        <title>Fomo Fighters Data</title>
        <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/1.13.4/css/jquery.dataTables.min.css">
        <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap" rel="stylesheet">
        <style>
            body { font-family: 'Roboto', sans-serif; background-color: #1e1e1e; color: #e0e0e0; margin: 0; display: flex; height: 100vh; overflow: hidden; }
            .sidebar { width: 250px; background-color: #252526; overflow-y: auto; border-right: 1px solid #333; display: flex; flex-direction: column; flex-shrink: 0; }
            .sidebar h2 { padding: 20px; margin: 0; color: #4caf50; font-size: 18px; text-align: center; border-bottom: 1px solid #333; }
            .nav-btn { background: none; border: none; color: #b0b0b0; padding: 12px 20px; text-align: left; width: 100%; cursor: pointer; transition: 0.2s; font-size: 14px; border-left: 3px solid transparent; }
            .nav-btn:hover { background-color: #2d2d30; color: white; }
            .nav-btn.active { background-color: #37373d; color: #fff; border-left: 3px solid #4caf50; font-weight: 500; }
            .content { flex: 1; padding: 20px; overflow-y: auto; background-color: #1e1e1e; }
            .tab-content { display: none; animation: fadeIn 0.3s; }
            .tab-content.active { display: block; }
            .update-time { font-size: 12px; color: #666; text-align: center; padding: 10px; }
            
            /* DataTables Dark Mode Overrides */
            table.dataTable { width: 100% !important; background-color: #252526; border-collapse: collapse; color: #ccc; }
            table.dataTable thead th { background-color: #333; color: #fff; border-bottom: 2px solid #444; padding: 12px; }
            table.dataTable tbody td { background-color: #252526; border-bottom: 1px solid #333; padding: 10px; }
            table.dataTable tbody tr:hover td { background-color: #2d2d30; }
            .dataTables_wrapper .dataTables_length, .dataTables_wrapper .dataTables_filter, 
            .dataTables_wrapper .dataTables_info, .dataTables_wrapper .dataTables_processing, 
            .dataTables_wrapper .dataTables_paginate { color: #aaa !important; margin-bottom: 10px; }
            .dataTables_wrapper .dataTables_filter input { background-color: #333; border: 1px solid #444; color: white; padding: 5px; border-radius: 4px; }
            
            @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
            ::-webkit-scrollbar { width: 10px; height: 10px; }
            ::-webkit-scrollbar-track { background: #1e1e1e; }
            ::-webkit-scrollbar-thumb { background: #444; border-radius: 5px; }
            ::-webkit-scrollbar-thumb:hover { background: #555; }
        </style>
    </head>
    """
    
    first = True
    for name, df in data_frames.items():
        clean_name = name.replace("db", "")
        active_class = "active" if first else ""
        nav_buttons += f'<button class="nav-btn {active_class}" onclick="openTab(\'{name}\', this)">{clean_name}</button>'
        table_html = df.to_html(index=False, table_id=f"table_{name}", classes="display compact", escape=False)
        tables_html += f'<div id="{name}" class="tab-content {active_class}"><h3>{clean_name}</h3>{table_html}</div>'
        first = False

    script = """
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <script src="https://cdn.datatables.net/1.13.4/js/jquery.dataTables.min.js"></script>
    <script>
        function openTab(tabName, btn) {
            $('.tab-content').removeClass('active');
            $('.nav-btn').removeClass('active');
            $('#' + tabName).addClass('active');
            $(btn).addClass('active');
            var tableId = '#table_' + tabName;
            if ( ! $.fn.DataTable.isDataTable( tableId ) ) {
                $(tableId).DataTable({ "pageLength": 25, "lengthMenu": [[10, 25, 50, 100, -1], [10, 25, 50, 100, "All"]], "scrollX": true });
            }
        }
        $(document).ready(function() {
            var firstTab = $('.tab-content').first().attr('id');
            if(firstTab) {
                $('#table_' + firstTab).DataTable({ "pageLength": 25, "lengthMenu": [[10, 25, 50, 100, -1], [10, 25, 50, 100, "All"]], "scrollX": true });
            }
        });
    </script>
    """
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return f"""<!DOCTYPE html>
    <html>
    {head}
    <body>
        <div class="sidebar">
            <h2>📊 Game Data</h2>
            <div class="update-time">Updated: {now}</div>
            {nav_buttons}
        </div>
        <div class="content">
            {tables_html}
        </div>
        {script}
    </body>
    </html>
    """

def push_to_git():
    """Отправляет изменения в GitHub"""
    try:
        # Добавляем index.html
        subprocess.run(["git", "add", OUTPUT_FILENAME], check=True)
        # Коммитим с датой
        msg = f"Auto-update stats: {datetime.now().strftime('%Y-%m-%d')}"
        subprocess.run(["git", "commit", "-m", msg], check=False) # check=False, если нечего коммитить
        # Пушим
        subprocess.run(["git", "push"], check=True)
        return True, "Git push successful"
    except Exception as e:
        return False, str(e)

def update_website_logic(raw_json_data):
    """Главная функция, вызываемая ботом"""
    if not raw_json_data:
        return False, "No data received"

    try:
        # 1. Парсинг данных (как было в скрипте)
        # В raw_json_data придет {'dbs': { 'dbBuildings': [...], ... }} 
        # Или сразу словарь, смотря как вернет API. Обычно API вернет {'success': True, 'data': {...}}
        
        # Предполагаем, что сюда передается уже 'data' часть ответа
        data = raw_json_data 
        
        trans_map = build_translation_map(data)
        prepared_dfs = {}
        
        for key, value in data.items():
            if isinstance(value, dict):
                df = pd.DataFrame(list(value.items()), columns=['Parameter', 'Value'])
                prepared_dfs[key] = df
            elif isinstance(value, list) and len(value) > 0:
                first = value[0]
                if 'levels' in first and isinstance(first['levels'], list):
                    prepared_dfs[key] = process_nested(value, trans_map)
                elif 'counts' in first and isinstance(first['counts'], list):
                    prepared_dfs[key] = process_parallel(value)
                else:
                    prepared_dfs[key] = process_simple(value, trans_map)
            elif isinstance(value, list) and len(value) == 0:
                 prepared_dfs[key] = pd.DataFrame(columns=["No Data"])

        # 2. Генерация HTML
        html_content = generate_html_content(prepared_dfs)
        
        with open(OUTPUT_FILENAME, "w", encoding="utf-8") as f:
            f.write(html_content)
            
        # 3. Пуш в Гит
        success, msg = push_to_git()
        return success, msg
        
    except Exception as e:
        return False, f"Generator error: {str(e)}"