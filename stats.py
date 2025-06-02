# stats.py
from collections import Counter, defaultdict
from typing import List, Dict, Any, Tuple
import re

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
MAX_DEPTH = 20
MAX_CHARS = 60
MAX_PATHS = 500  # Лимит путей для предотвращения взрыва

LINK_TUPLE_SIZE = 7

# Регекс для подсчета слов
WORD_RE = re.compile(r'\S+')

def title(text: str, char: str = "=") -> str:
    """Создаёт заголовок с подчёркиванием"""
    return f"{text}\n{char * len(text)}"

def get_stats(locs: List[Loc]) -> str:
    if not locs:
        return f"\n{title('Статистика Квеста')}\n\nПусто. Грустно.\n"
    
    s = _collect_stats(locs)
    s['orphans'] = _get_orphans(locs)  # быстрое получение вместо поиска
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

def _get_orphans(locs: List[Loc]) -> List[str]:
    """Получает список сироток из готовых флагов"""
    return [loc.name for loc in locs if loc.name and hasattr(loc, 'orphan') and loc.orphan]

def _collect_stats(locs: List[Loc]) -> Dict[str, Any]:
    """Один проход - всё собираем оптимизированно"""
    s = {
        'total': len(locs), 'endings': 0, 'desc_chars': 0, 'desc_words': 0,
        'has_desc': 0, 'no_desc': [], 'cycles': set(), 'dups': set(),
        'links_total': 0, 'btn': 0, 'btn_local': 0, 'btn_menu': 0, 
        'goto': 0, 'proc': 0, 'auto': 0, 'phantoms': {}, 'empty_btns': {},
        'targets': defaultdict(int), 'link_counts': [], 'labels': [],
        'auto_links': [], 'max_desc': (0, ""), 'max_links': (0, ""),
        'desc_lens': [], 'label_lens': [], 'tech': 0, 'tech_names': [],
        'orphan': 0, 'orphan_names': []  # добавили счетчик сироток
    }
    
    for loc in locs:
        name = loc.name or f"ID_{loc.id}"
        
        # Базовая инфа
        if loc.end: 
            s['endings'] += 1
        if hasattr(loc, 'cycle') and loc.cycle: 
            s['cycles'].add(name)
        if hasattr(loc, 'dup') and loc.dup and loc.name: 
            s['dups'].add(loc.name)
        if hasattr(loc, 'tech') and loc.tech:  # счетчик техлокаций
            s['tech'] += 1
            s['tech_names'].append(name)
        if hasattr(loc, 'orphan') and loc.orphan:  # счетчик сироток
            s['orphan'] += 1
            s['orphan_names'].append(name)
        
        # Описания - оптимизированный подсчет
        desc = getattr(loc, 'desc', "")
        if desc and desc != "Нет описания":
            s['has_desc'] += 1
            desc_len = len(desc)
            s['desc_chars'] += desc_len
            s['desc_lens'].append(desc_len)
            
            # Быстрый подсчёт слов через regex
            word_cnt = len(WORD_RE.findall(desc))
            s['desc_words'] += word_cnt
            
            if desc_len > s['max_desc'][0]:
                s['max_desc'] = (desc_len, name)
        else:
            s['no_desc'].append(name)
        
        # Связи - работаем напрямую с кортежами
        links = getattr(loc, 'links', [])
        link_cnt = len(links)
        s['link_counts'].append((name, link_cnt))
        if link_cnt > s['max_links'][0]:
            s['max_links'] = (link_cnt, name)
        
        empty_cnt = 0
        loc_phantoms = {}
        
        for link_tuple in links:
            if not link_tuple or len(link_tuple) < LINK_TUPLE_SIZE:
                continue
            
            # Прямой доступ к кортежу вместо namedtuple
            link_id, target, link_type, label, phantom, menu, local = link_tuple
            
            s['links_total'] += 1
            
            # Обработка по типу
            if link_type == 'btn':
                s['btn'] += 1
                if local: s['btn_local'] += 1
                if menu: s['btn_menu'] += 1
                
                if label and label.strip():
                    label_len = len(label)
                    word_cnt = len(WORD_RE.findall(label))
                    s['labels'].append((label_len, label, name, word_cnt))
                    s['label_lens'].append(label_len)
                else:
                    empty_cnt += 1
                    
            elif link_type == 'goto':
                s['goto'] += 1
            elif link_type == 'proc':
                s['proc'] += 1
            elif link_type == 'auto':
                s['auto'] += 1
                if target:
                    s['auto_links'].append((name, target))
            
            # Фантомы и цели
            if phantom and target:
                if link_type not in loc_phantoms:
                    loc_phantoms[link_type] = []
                loc_phantoms[link_type].append(target)
            elif target:
                s['targets'][target] += 1
        
        if loc_phantoms: 
            s['phantoms'][name] = loc_phantoms
        if empty_cnt: 
            s['empty_btns'][name] = empty_cnt
    
    return s

def _analyze_graph(locs: List[Loc]) -> Dict[str, Any]:
    """Оптимизированный анализ графа"""
    if not locs:
        return {}
    
    # Строим минимальный граф, добавляем метки только при необходимости
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
            
        for link_tuple in getattr(loc, 'links', []):
            if not link_tuple or len(link_tuple) < LINK_TUPLE_SIZE:
                continue
                
            link_id, target, link_type, label, phantom, menu, local = link_tuple
            if not target or phantom:
                continue
            
            # Определяем надпись для перехода
            if link_type == "btn" and label and label.strip():
                link_label = label.strip()
            else:
                link_label = {"goto": "goto", "auto": "авто", "proc": "proc"}.get(link_type, link_type)
            
            graph[name].append((target, link_label))
    
    if not graph:
        return {}
    
    start = locs[0].name if locs[0].name else "start"
    
    # Базовая статистика
    total_connections = sum(len(targets) for targets in graph.values())
    s = {
        'total_connections': total_connections,
        'avg_connections': total_connections / len(all_locs) if all_locs else 0,
        'reachable_count': 0,
        'paths_to_endings': {},
        'max_depth': 0,
        'total_paths': 0
    }
    
    # Достижимость от старта
    reachable = _bfs_reachable(graph, start)
    s['reachable_count'] = len(reachable)
    
    # Анализ путей до концовок с лимитом
    total_found_paths = 0
    for end in endings:
        if total_found_paths >= MAX_PATHS:
            break
            
        paths = _find_paths_limited(graph, start, end, MAX_DEPTH, MAX_PATHS - total_found_paths)
        if paths:
            # Считаем шаги как количество связей (длина пути - 1)
            path_steps = [len(p) - 1 for p in paths]  # Шаги = связи между локациями
            shortest_idx = path_steps.index(min(path_steps))
            longest_idx = path_steps.index(max(path_steps))
            
            s['paths_to_endings'][end] = {
                'count': len(paths),
                'shortest_len': path_steps[shortest_idx],
                'longest_len': path_steps[longest_idx], 
                'shortest_path': paths[shortest_idx],
                'longest_path': paths[longest_idx],
                'avg_length': sum(path_steps) / len(path_steps)
            }
            s['total_paths'] += len(paths)
            s['max_depth'] = max(s['max_depth'], max(path_steps))
            total_found_paths += len(paths)
    
    return s

def _find_paths_limited(graph: Dict[str, List[Tuple[str, str]]], start: str, end: str, max_depth: int, max_paths: int) -> List[List[Tuple[str, str]]]:
    """Находит пути с лимитом количества"""
    if start not in graph:
        return []
    
    paths = []
    
    def dfs(node: str, path: List[Tuple[str, str]], visited: set):
        if len(paths) >= max_paths or len(path) > max_depth:
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
    
    dfs(start, [(start, "")], {start})
    return paths

def _bfs_reachable(graph: Dict[str, List[Tuple[str, str]]], start: str) -> set:
    """Унифицированный BFS поиск"""
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

def _format_path_with_labels(path: List[Tuple[str, str]]) -> str:
    """Форматирует путь с надписями"""
    if not path:
        return ""
    
    parts = []
    for i, (loc, label) in enumerate(path):
        if i == 0:
            parts.append(f'"{loc}"')
        else:
            parts.append(f'→ ({label}) → "{loc}"' if label else f'→ "{loc}"')
    
    return ' '.join(parts)

def _bar(val: int, max_val: int, width: int = BAR_WIDTH) -> str:
    """ASCII прогрессбар"""
    if max_val == 0:
        return "█" * width + " 0%"
    
    ratio = val / max_val
    filled = int(ratio * width)
    bar = "█" * filled + "─" * (width - filled)
    return f"{bar} {ratio * 100:.1f}%"

def _format_top_items(items: List[tuple], val_idx: int, item_formatter) -> List[str]:
    """Универсальное форматирование топ-списков"""
    if not items:
        return []
    
    parts = []
    max_val = items[0][val_idx] if items else 0
    
    for item in items:
        val = item[val_idx]
        line = item_formatter(item)
        
        padding = MAX_CHARS - len(line)
        if padding > 0:
            line += " " * padding
        
        bar = _bar(val, max_val)
        parts.append(f"{line} {bar}")
    
    return parts

def _add_loc_section(lines: List[str], s: Dict[str, Any]):
    """Секция локаций"""
    lines.append(f"\n{title('Статистика по Локациям', '=')}\n")
    
    # Техлокации
    if s['tech']:
        names = ', '.join(f'"{n}"' for n in s['tech_names'])
        lines.append(f"Технических локаций: {s['tech']} шт. ({names})")
        
    # Локации-сиротки
    # if s['orphan']:
    #     names = ', '.join(f'"{n}"' for n in s['orphan_names'])
    #     lines.append(f"Локации-сиротки: {s['orphan']} шт. ({names})")
    
    # Среднее описание  
    if s['has_desc']:
        avg_w = s['desc_words'] / s['has_desc']
        avg_c = s['desc_chars'] / s['has_desc'] 
        lines.append(f"Средняя длина описания ({s['has_desc']} лок.): {avg_w:.1f} слов, {avg_c:.1f} симв.\n")
    
    # Максимальное описание
    if s['max_desc'][0]:
        lines.append(f"{title('Самое большое описание', '-')}\n")
        lines.append(f'- "{s["max_desc"][1]}" ({s["max_desc"][0]} симв.)\n')
    
    # Без описаний
    if s['no_desc']:
        names = ', '.join(f'"{n}"' for n in s['no_desc'])
        lines.append(f"Без описания: {len(s['no_desc'])} шт. ({names})\n")
    
    # Развилки - одна сортировка
    sorted_links = sorted(s['link_counts'], key=lambda x: x[1], reverse=True)
    branches = [(n, c) for n, c in sorted_links if c > BRANCH_MIN]
    if branches:
        top_branches = branches[:TOP_N]
        lines.append(f"{title(f'Развилки (>{BRANCH_MIN} связей, топ {len(top_branches)})', '-')}\n")
        
        formatter = lambda item: f'- "{item[0]}": {item[1]} связей'
        lines.extend(_format_top_items(top_branches, 1, formatter))
        lines.append("")
    
    # Популярные цели
    if s['targets']:
        top_targets = Counter(s['targets']).most_common(TOP_N)
        lines.append(f"{title(f'Популярные локации (топ {len(top_targets)})', '-')}\n")
        
        formatter = lambda item: f'- "{item[0]}": {item[1]} ссылок'
        lines.extend(_format_top_items(top_targets, 1, formatter))
        lines.append("")
              
def _add_link_section(lines: List[str], s: Dict[str, Any]):
    """Секция связей"""
    lines.append(f"\n{title('Статистика по переходам', '=')}\n")
    
    # Среднее и максимум
    if s['total']:
        avg = s['links_total'] / s['total']
        lines.append(f"Среднее количество переходов на локацию: {avg:.1f} шт.")
        lines.append(f'Максимум переходов: {s["max_links"][0]} шт. (из "{s["max_links"][1]}")\n')
    
    # Детали по типам с прогрессбарами
    if s['links_total']:
        lines.append(f"Переходов всего: {s['links_total']} шт.")
        
        # Собираем данные для баров
        type_data = []
        if s['btn']:
            details = []
            if s['btn_local']: details.append(f"{s['btn_local']} локальных")
            if s['btn_menu']: details.append(f"{s['btn_menu']} меню")
            extra = f" ({', '.join(details)})" if details else ""
            type_data.append((s['btn'], f"Кнопки: {s['btn']} шт.{extra}"))
        
        for typ, cnt in [('goto', s['goto']), ('proc', s['proc']), ('auto', s['auto'])]:
            if cnt:
                type_data.append((cnt, f"{typ.title()}: {cnt} шт."))
        
        # Выводим с барами - фиксим max_val
        if type_data:
            max_val = s['links_total']  # Фикс: используем общее количество
            for val, desc in type_data:
                padding = MAX_CHARS - len(f"- {desc}")
                if padding > 0:
                    desc += " " * padding
                bar = _bar(val, max_val)
                lines.append(f"- {desc} {bar}")
        lines.append("")

    # Анализ графа
    if 'graph_stats' in s and s['graph_stats']:
        gs = s['graph_stats']
        lines.append(f"{title('Анализ путей и связности', '-')}\n")
        lines.append(f"Достижимо от старта: {gs['reachable_count']} из {s['total']} локаций")
        
        if gs['total_paths']:
            lines.append(f"Всего возможных путей до концовок: {gs['total_paths']} шт.")
            lines.append(f"Максимальная глубина прохождения: {gs['max_depth']} шагов\n")
            
            # Детали по концовкам с путями
            for end, info in gs['paths_to_endings'].items():
                count_word = "путь" if info["count"] == 1 else ("пути" if info["count"] < 5 else "путей")
                lines.append(f'До концовки "{end}": {info["count"]} {count_word}')
                
                # Кратчайший путь
                short_path = _format_path_with_labels(info['shortest_path'])
                lines.append(f"Кратчайший ({info['shortest_len']} шагов):")
                lines.append(f"~~~\n{short_path}\n~~~")

                # Длиннейший только если отличается
                if info['longest_len'] > info['shortest_len']:
                    long_path = _format_path_with_labels(info['longest_path'])
                    lines.append(f"Длиннейший ({info['longest_len']} шагов):")
                    lines.append(f"~~~\n{long_path}\n~~~")
                    
                if info['count'] > 1:
                    lines.append(f"Средняя длина: {info['avg_length']:.1f} шагов")
                lines.append("")
        else:
            lines.append("Путей до концовок не найдено.\n")

def _add_problems_section(lines: List[str], s: Dict[str, Any]):
    """Секция проблем"""
    lines.append(f"\n{title('Потенциальные Проблемы', '=')}\n")
    
    # Ранний выход если проблем нет
    if not any([s['cycles'], s['dups'], s['auto_links'], s['orphans'], s['phantoms'], s['empty_btns']]):
        lines.append("Проблем не найдено. Отлично!\n")
        return
    
    # Циклы
    if s['cycles']:
        cycle_list = sorted(s['cycles'])
        names = ', '.join(f'"{n}"' for n in cycle_list)
        lines.append(f"Самоссылки: {len(s['cycles'])} шт. ({names})\n")
    
    # Дубли
    if s['dups']:
        dup_list = sorted(s['dups'])
        names = ', '.join(f'"{n}"' for n in dup_list)
        lines.append(f"Дубликаты: {names} ({len(s['dups'])} шт.)\n")
    
    # Автосвязи
    if s['auto_links']:
        auto_list = ', '.join(f'"{src}" -> "{dst}"' for src, dst in sorted(s['auto_links']))
        lines.append(f"Автосвязи: {auto_list}\n")
    
    # Локации-сиротки
    if s['orphans']:
        names = ', '.join(f'"{n}"' for n in s['orphans'])
        lines.append(f"Локации-сиротки: {len(s['orphans'])} шт. ({names})\n")
    
    # Фантомы
    if s['phantoms']:
        lines.append(f"{title('Фантомные ссылки', '-')}\n")
        for loc, types in sorted(s['phantoms'].items()):
            lines.append(f'В "{loc}":')
            for typ, targets in sorted(types.items()):
                tlist = ', '.join(f'"{t}"' for t in sorted(set(targets)))
                lines.append(f"- {typ}: {tlist}")
            lines.append("")
    
    # Пустые кнопки
    if s['empty_btns']:
        lines.append(f"{title('Кнопки с пустыми надписями', '-')}\n")
        for loc, cnt in sorted(s['empty_btns'].items()):
            lines.append(f'- В "{loc}": {cnt} шт.')
        lines.append("")

def _add_link_labels_section(lines: List[str], s: Dict[str, Any]):
    """Секция надписей"""
    if not s['labels']: 
        return
    
    lines.append(f"\n{title('Анализ надписей кнопок', '=')}\n")
    
    # Среднее
    if s['label_lens']:
        avg = sum(s['label_lens']) / len(s['label_lens'])
        lines.append(f"Средняя длина: {avg:.1f} симв.\n")
    
    # Одна сортировка по длине
    sorted_labels = sorted(s['labels'], key=lambda x: x[0])
    
    # Самые длинные
    lines.append(f"{title('Самые длинные (топ-3)', '-')}\n")
    long_top = sorted_labels[-3:][::-1]  # Последние 3, в обратном порядке
    for length, text, loc, words in long_top:
        preview = text[:50] + "..." if len(text) > 50 else text
        lines.append(f'- "{preview}"')
        lines.append(f"  ({length} симв., {words} слов, в \"{loc}\")")
    lines.append("")
    
    # Самые короткие
    lines.append(f"{title('Самые короткие (топ-3)', '-')}\n")
    short_top = sorted_labels[:3]
    for length, text, loc, words in short_top:
        lines.append(f'- "{text}"')
        lines.append(f"  ({length} симв., {words} слов, в \"{loc}\")")
    lines.append("")
    
    # Очень длинные
    long_ones = [item for item in s['labels'] if item[0] > LONG_LABEL]
    if long_ones:
        lines.append(f"{title(f'Длиннее {LONG_LABEL} символов ({len(long_ones)} шт.)', '-')}\n")
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