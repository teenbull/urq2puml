# stats.py
from collections import Counter
from typing import List, Dict, Any, Tuple

try:
    from .urq_parser import Loc 
except ImportError:
    from urq_parser import Loc 
except Exception: 
    class Loc: pass

# Константы
BRANCH_MIN = 3
LONG_LABEL = 80
TOP_N = 5
BAR_WIDTH = 20

def title(text: str, char: str = "=") -> str:
    """Создаёт заголовок с подчёркиванием"""
    return f"{text}\n{char * len(text)}"

def get_stats(locs: List[Loc]) -> str:
    if not locs:
        return f"\n{title('Статистика Квеста')}\n\nПусто. Грустно.\n"
    
    s = _collect_stats(locs)
    
    # Анализируем структуру
    s['orphans'] = _find_orphans(locs)
    s['graph_stats'] = _analyze_graph(locs)
    
    lines = [title("Общая Статистика Квеста")]
    lines.append(f"Локации: {s['total']} шт.")
    if s['endings']: 
        lines.append(f"Концовки: {s['endings']} шт.")
    if s['desc_chars']:
        lines.append(f"Символов в pln/p: {s['desc_chars']}")
    
    _add_loc_section(lines, s)
    _add_link_section(lines, s)  
    _add_link_labels_section(lines, s)
    _add_problems_section(lines, s)
    
    return "\n".join(lines)

def _collect_stats(locs: List[Loc]) -> Dict[str, Any]:
    """Один проход - всё собираем"""
    s = {
        'total': len(locs), 'endings': 0, 'desc_chars': 0, 'desc_words': 0,
        'has_desc': 0, 'no_desc': [], 'cycles': set(), 'dups': set(),
        'links_total': 0, 'btn': 0, 'btn_local': 0, 'btn_menu': 0, 
        'goto': 0, 'proc': 0, 'auto': 0, 'phantoms': {}, 'empty_btns': {},
        'targets': Counter(), 'descs': [], 'link_counts': [], 'labels': [],
        'auto_links': [], 'orphans': []
    }
    
    for loc in locs:
        name = loc.name or f"ID_{loc.id}"
        
        # Базовая инфа
        if loc.end: s['endings'] += 1
        if getattr(loc, 'cycle', False): s['cycles'].add(name)
        if getattr(loc, 'dup', False) and loc.name: s['dups'].add(loc.name)
        
        # Описания
        desc = getattr(loc, 'desc', "")
        if desc and desc != "Нет описания":
            s['has_desc'] += 1
            s['desc_chars'] += len(desc)
            words = len(desc.split())
            s['desc_words'] += words
            s['descs'].append((len(desc), name, words))
        else:
            s['no_desc'].append(name)
        
        # Связи
        links = getattr(loc, 'links', [])
        s['link_counts'].append((name, len(links)))
        
        empty_cnt = 0
        loc_phantoms = {}
        
        for link in links:
            if not isinstance(link, tuple) or len(link) < 7: 
                continue
            
            _, target, ltype, label, phantom, menu, local = link
            s['links_total'] += 1
            
            # Типы
            if ltype == "btn":
                s['btn'] += 1
                if local: s['btn_local'] += 1
                if menu: s['btn_menu'] += 1
                
                if not (label and label.strip()):
                    empty_cnt += 1
                else:
                    clean = label.strip()
                    words = len(clean.split())
                    s['labels'].append((len(clean), clean, name, words))
            elif ltype == "goto": s['goto'] += 1
            elif ltype == "proc": s['proc'] += 1  
            elif ltype == "auto": 
                s['auto'] += 1
                if target:
                    s['auto_links'].append((name, target))
            
            # Фантомы и цели
            if phantom and target:
                loc_phantoms.setdefault(ltype, []).append(target)
            elif target:
                s['targets'][target] += 1
        
        if loc_phantoms: s['phantoms'][name] = loc_phantoms
        if empty_cnt: s['empty_btns'][name] = empty_cnt
    
    return s

def _analyze_graph(locs: List[Loc]) -> Dict[str, Any]:
    """Полный анализ графа переходов с надписями"""
    if not locs:
        return {}
    
    # Строим граф основных переходов с надписями
    graph = {}
    all_locs = set()
    endings = []
    
    for loc in locs:
        name = loc.name
        if not name:
            continue
            
        all_locs.add(name)
        graph[name] = []
        if loc.end:
            endings.append(name)
            
        for link in getattr(loc, 'links', []):
            if len(link) >= 7:
                _, target, ltype, label, phantom, menu, local = link
                # Берём все типы переходов, кроме фантомных
                if target and not phantom:
                    # Определяем надпись для перехода
                    if ltype == "btn" and label and label.strip():
                        link_label = label.strip()
                    elif ltype == "goto":
                        link_label = "goto"
                    elif ltype == "auto":
                        link_label = "авто"
                    elif ltype == "proc":
                        link_label = "proc"
                    else:
                        link_label = ltype
                    
                    graph[name].append((target, link_label))
    
    start = locs[0].name if locs[0].name else "start"
    
    # Базовая статистика
    stats = {
        'total_connections': sum(len(targets) for targets in graph.values()),
        'avg_connections': 0,
        'reachable_count': 0,
        'paths_to_endings': {},
        'max_depth': 0,
        'total_paths': 0
    }
    
    if all_locs:
        stats['avg_connections'] = stats['total_connections'] / len(all_locs)
    
    # Достижимость от старта
    reachable = _bfs_reachable_with_labels(graph, start)
    stats['reachable_count'] = len(reachable)
    
    # Анализ путей до концовок
    for end in endings:
        paths = _find_all_paths_with_labels(graph, start, end, max_depth=20)
        if paths:
            shortest = min(paths, key=len)
            longest = max(paths, key=len)
            stats['paths_to_endings'][end] = {
                'count': len(paths),
                'shortest_len': len(shortest),
                'longest_len': len(longest),
                'shortest_path': shortest,
                'longest_path': longest,
                'avg_length': sum(len(p) for p in paths) / len(paths)
            }
            stats['total_paths'] += len(paths)
            stats['max_depth'] = max(stats['max_depth'], max(len(p) for p in paths))
    
    return stats

def _find_all_paths_with_labels(graph: Dict[str, List[Tuple[str, str]]], start: str, end: str, max_depth: int = 15) -> List[List[Tuple[str, str]]]:
    """Находит все пути с надписями без циклов до определённой глубины"""
    if start not in graph:
        return []
    
    paths = []
    
    def dfs(node: str, path: List[Tuple[str, str]], visited: set):
        if len(path) > max_depth:  # Защита от слишком длинных путей
            return
            
        if node == end:
            paths.append(path[:])
            return
        
        for target, label in graph.get(node, []):
            if target not in visited:
                path.append((target, label))
                visited.add(target)
                dfs(target, path, visited)
                path.pop()
                visited.remove(target)
    
    # Начальный путь содержит только стартовую локацию
    dfs(start, [(start, "")], {start})
    return paths

def _bfs_reachable_with_labels(graph: Dict[str, List[Tuple[str, str]]], start: str) -> set:
    """BFS поиск всех достижимых локаций"""
    if start not in graph:
        return set()
    
    reachable = {start}
    queue = [start]
    
    while queue:
        current = queue.pop(0)
        for target, _ in graph.get(current, []):
            if target not in reachable:
                reachable.add(target)
                queue.append(target)
    
    return reachable

def _find_orphans(locs: List[Loc]) -> List[str]:
    """Находит локации-сиротки через BFS от стартовой"""
    if not locs:
        return []
    
    # Строим граф всех связей (включая фантомные)
    graph = {}
    all_names = set()
    
    for loc in locs:
        name = loc.name
        if not name:
            continue
            
        all_names.add(name)
        graph[name] = []
        
        for link in getattr(loc, 'links', []):
            if len(link) >= 2:
                target = link[1]
                if target:
                    graph[name].append(target)
    
    # Находим достижимые (простой граф без надписей для этой задачи)
    start_name = locs[0].name
    if not start_name:
        return list(all_names)
    
    reachable = _bfs_reachable_simple(graph, start_name)
    return sorted(all_names - reachable)

def _bfs_reachable_simple(graph: Dict[str, List[str]], start: str) -> set:
    """BFS поиск для простого графа"""
    if start not in graph:
        return set()
    
    reachable = {start}
    queue = [start]
    
    while queue:
        current = queue.pop(0)
        for target in graph.get(current, []):
            if target not in reachable:
                reachable.add(target)
                queue.append(target)
    
    return reachable

def _format_path_with_labels(path: List[Tuple[str, str]]) -> str:
    """Форматирует путь с надписями"""
    if not path:
        return ""
    
    result = []
    for i, (loc, label) in enumerate(path):
        if i == 0:
            result.append(f'"{loc}"')
        else:
            if label:
                result.append(f'→ ({label}) → "{loc}"')
            else:
                result.append(f'→ "{loc}"')
    
    return ' '.join(result)

def _bar(val: int, max_val: int, width: int = BAR_WIDTH) -> str:
    """ASCII прогрессбар"""
    if max_val == 0:
        return "█" * width + " 0%"
    
    pct = (val / max_val) * 100
    filled = int((val / max_val) * width)
    bar = "█" * filled + "─" * (width - filled)
    return f"{bar} {pct:.1f}%"

def _format_top(items: List[tuple], val_idx: int = 0, max_chars: int = 60) -> List[str]:
    """Топ-список с барами"""
    if not items:
        return []
    
    lines = []
    max_val = items[0][val_idx] if items else 0
    
    for item in items:
        val = item[val_idx]
        
        # Форматируем строку
        if len(item) == 3 and val_idx == 0:  # Описания (chars, name, words)
            chars, name, words = item
            line = f'- "{name}" ({words} слов, {chars} симв.)'
        elif len(item) == 2:  # Связи/цели (name, count)
            name, cnt = item
            line = f'- "{name}": {cnt} связей' if 'связ' in str(item) else f'- "{name}": {cnt} ссылок'
        else:
            line = f'- {item}'
        
        # Отступ + бар
        padding = max_chars - len(line)
        if padding > 0:
            line += " " * padding
        
        progress = _bar(val, max_val)
        lines.append(f"{line} {progress}")
    
    return lines

def _format_label_top(items: List[tuple], val_idx: int = 0, show_bars: bool = True) -> List[str]:
   """Топ надписей с переносом деталей"""
   if not items:
       return []
   
   lines = []
   max_val = items[0][val_idx] if items else 0
   
   for item in items:
       length, text, loc, words = item
       
       # Первая строка - только надпись
       preview = text[:50] + "..." if len(text) > 50 else text
       lines.append(f'- "{preview}"')
       
       # Вторая строка - детали с баром
       detail = f"  ({length} симв., {words} слов, в \"{loc}\")"
       
       if show_bars:
           padding = 70 - len(detail)
           if padding > 0:
               detail += " " * padding
           progress = _bar(length, max_val)
           lines.append(f"{detail} {progress}")
       else:
           lines.append(detail)
   
   return lines

def _add_loc_section(lines: List[str], s: Dict[str, Any]):
    """Секция локаций"""
    lines.append(f"\n{title('Статистика по Локациям', '=')}")
    lines.append("")
    
    # Среднее описание
    if s['has_desc']:
        avg_w = s['desc_words'] / s['has_desc']
        avg_c = s['desc_chars'] / s['has_desc'] 
        lines.append(f"Средняя длина описания ({s['has_desc']} лок.): {avg_w:.1f} слов, {avg_c:.1f} симв.")
        lines.append("")
    
    # Топ описаний
    if s['descs']:
        top = sorted(s['descs'], reverse=True)[:TOP_N]
        lines.append(title(f"Самые большие описания (топ {len(top)})", "-"))
        lines.append("")
        for line in _format_top(top, val_idx=0):
            lines.append(line)
        lines.append("")
    
    # Без описаний
    if s['no_desc']:
        names = ', '.join(f'"{n}"' for n in sorted(s['no_desc']))
        lines.append(f"Без описания: {len(s['no_desc'])} шт. ({names})")
        lines.append("")
    
    # Развилки
    branches = [(n, c) for n, c in s['link_counts'] if c > BRANCH_MIN]
    if branches:
        top = sorted(branches, key=lambda x: x[1], reverse=True)[:TOP_N]
        lines.append(title(f"Развилки (>{BRANCH_MIN} связей, топ {len(top)})", "-"))
        lines.append("")
        for line in _format_top(top, val_idx=1):
            lines.append(line)
        lines.append("")
    
    # Популярные цели  
    if s['targets']:
        top = s['targets'].most_common(TOP_N)
        lines.append(title(f"Популярные локации (топ {len(top)})", "-"))
        lines.append("")
        for line in _format_top(top, val_idx=1):
            lines.append(line)
        lines.append("")

def _add_link_section(lines: List[str], s: Dict[str, Any]):
   """Секция связей"""
   lines.append(f"\n{title('Статистика по переходам', '=')}")
   lines.append("")
   
   # Среднее и максимум
   if s['total']:
       avg = s['links_total'] / s['total']
       lines.append(f"Среднее количество переходов на локацию: {avg:.1f} шт.")
       
       max_name, max_cnt = max(s['link_counts'], key=lambda x: x[1])
       lines.append(f'Максимум переходов: {max_cnt} шт. (из "{max_name}")')
       lines.append("")
   
   # Анализ графа (новая секция)
   if 'graph_stats' in s:
       gs = s['graph_stats']
       lines.append(title("Анализ путей и связности", "-"))
       lines.append("")
       lines.append(f"Достижимо от старта: {gs['reachable_count']} из {s['total']} локаций")
       
       if gs['total_paths']:
           lines.append(f"Всего возможных путей до концовок: {gs['total_paths']} шт.")
           lines.append(f"Максимальная глубина прохождения: {gs['max_depth']} переходов")
           lines.append("")
           
           # Детали по концовкам с путями
           for end, info in gs['paths_to_endings'].items():
               count_word = "путь" if info["count"] == 1 else ("пути" if info["count"] < 5 else "путей")
               lines.append(f'До концовки "{end}": {info["count"]} {count_word}')
               
               # Кратчайший путь с надписями
               short_path = _format_path_with_labels(info['shortest_path'])
               
               lines.append(f"Кратчайший ({info['shortest_len']} шагов):")
               lines.append(f"~~~\n{short_path}\n~~~")

               # Длиннейший только если отличается
               if info['longest_len'] > info['shortest_len']:
                   long_path = _format_path_with_labels(info['longest_path'])
                   lines.append(f"Длиннейший ({info['longest_len']} шагов):")
                   lines.append(f"~~~\n{long_path}\n~~~")
               if info['count'] > 1:
                   avg_len = int(round(info['avg_length']))
                   lines.append(f"Средняя длина: {avg_len} шагов")
               lines.append("")
       else:
           lines.append("Путей до концовок не найдено.")
           lines.append("")
   
   # Детали по типам с прогрессбарами
   if s['links_total']:
       lines.append(f"Переходов всего: {s['links_total']} шт.")
       
       # Собираем типы для баров
       types_data = []
       if s['btn']:
           details = []
           if s['btn_local']: details.append(f"{s['btn_local']} локальных")
           if s['btn_menu']: details.append(f"{s['btn_menu']} меню")
           extra = f" ({', '.join(details)})" if details else ""
           types_data.append((s['btn'], f"Кнопки: {s['btn']} шт.{extra}"))
       
       for typ, cnt in [('goto', s['goto']), ('proc', s['proc']), ('auto', s['auto'])]:
           if cnt:
               types_data.append((cnt, f"{typ.title()}: {cnt} шт."))
       
       # Выводим с барами
       for cnt, text in types_data:
           line = f"- {text}"
           padding = 60 - len(line)
           if padding > 0:
               line += " " * padding
           bar = _bar(cnt, s['links_total'])
           lines.append(f"{line} {bar}")
       
       lines.append("")
def _add_problems_section(lines: List[str], s: Dict[str, Any]):
    """Секция проблем"""
    lines.append(f"\n{title('Потенциальные Проблемы', '=')}")
    lines.append("")
    
    # Циклы
    if s['cycles']:
        names = ', '.join(f'"{n}"' for n in sorted(s['cycles']))
        lines.append(f"Самоссылки: {len(s['cycles'])} шт. ({names})")
        lines.append("")
    
    # Дубли
    if s['dups']:
        names = ', '.join(f'"{n}"' for n in sorted(s['dups']))
        lines.append(f"Дубликаты: {names} ({len(s['dups'])} шт.)")
        lines.append("")
    
    # Автосвязи
    if s['auto_links']:
        auto_list = ', '.join(f'"{src}" -> "{dst}"' for src, dst in sorted(s['auto_links']))
        lines.append(f"Автосвязи: {auto_list}")
        lines.append("")
    
    # Локации-сиротки
    if s['orphans']:
        names = ', '.join(f'"{n}"' for n in sorted(s['orphans']))
        lines.append(f"Локации-сиротки: {len(s['orphans'])} шт. ({names})")
        lines.append("")
    
    # Фантомы
    if s['phantoms']:
        lines.append(title("Фантомные ссылки", "-"))
        lines.append("")
        for loc, types in sorted(s['phantoms'].items()):
            lines.append(f'В "{loc}":')
            for typ, targets in sorted(types.items()):
                tlist = ', '.join(f'"{t}"' for t in sorted(set(targets)))
                lines.append(f"- {typ}: {tlist}")
            lines.append("")
    else:
        lines.append("Фантомных ссылок нет.")
        lines.append("")
    
    # Пустые кнопки
    if s['empty_btns']:
        lines.append(title("Кнопки с пустыми надписями", "-"))
        lines.append("")
        for loc, cnt in sorted(s['empty_btns'].items()):
            lines.append(f'- В "{loc}": {cnt} шт.')
        lines.append("")

def _add_link_labels_section(lines: List[str], s: Dict[str, Any]):
    """Секция надписей"""
    if not s['labels']: 
        return
    
    lines.append(f"\n{title('Анализ надписей кнопок', '=')}")
    lines.append("")
    
    # Среднее
    avg = sum(x[0] for x in s['labels']) / len(s['labels'])
    lines.append(f"Средняя длина: {avg:.1f} симв.")
    lines.append("")
    
    # Топы
    by_len = sorted(s['labels'])
    
    lines.append(title("Самые длинные (топ-3)", "-"))
    lines.append("")
    long_top = by_len[-3:][::-1]
    for line in _format_label_top(long_top, val_idx=0, show_bars=True):
        lines.append(line)
    lines.append("")
    
    lines.append(title("Самые короткие (топ-3)", "-"))
    lines.append("")
    short_top = by_len[:3]
    if short_top:
        for line in _format_label_top(short_top, val_idx=0, show_bars=False):
            lines.append(line)
    lines.append("")
    
    # Очень длинные
    long_ones = [(l, t, loc, w) for l, t, loc, w in s['labels'] if l > LONG_LABEL]
    if long_ones:
        lines.append(title(f"Длиннее {LONG_LABEL} символов ({len(long_ones)} шт.)", "-"))
        lines.append("")
        for length, text, loc, words in long_ones:
            lines.append(f'- "{loc}" - "{text}"')
        lines.append("")

# Тест
if __name__ == '__main__':
    class MockLoc:
        def __init__(self, name, id="mock", desc="Нет описания", end=False, cycle=False, dup=False, links=None):
            self.name = name
            self.id = id  
            self.desc = desc
            self.end = end
            self.cycle = cycle
            self.dup = dup
            self.links = links or []

    test_locs = [
        MockLoc("start", desc="Стартовая локация с описанием.", links=[
            (None, "loc_a", "btn", "Кнопка А", False, False, False),
            (None, "target", "btn", "К цели", False, False, False)
        ]),
        MockLoc("loc_a", desc="Локация А", links=[
            (None, "phantom", "btn", "", True, False, False),
            (None, "target", "goto", "", False, False, False)
        ]),
        MockLoc("target", desc="Популярная цель", end=True),
        MockLoc("cycle", cycle=True, links=[(None, "cycle", "btn", "Сам в себя", False, False, False)]),
        MockLoc("start", desc="Дубликат", dup=True),  # дубль имени
        MockLoc("orphan", desc="Сиротка без связей")  # недостижимая
    ]
    
    print(get_stats(test_locs))