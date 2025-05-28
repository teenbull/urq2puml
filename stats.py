# stats.py
from collections import Counter
import re 
from typing import List, Dict, Any, Tuple, Set 

try:
    from .urq_parser import Loc 
except ImportError:
    from urq_parser import Loc 
except Exception: 
    class Loc: pass 
    

# --- Вспомогательные функции для сбора данных (без изменений) ---
def _collect_basic_stats(locs_data: List[Loc]) -> Dict[str, Any]:
    stats = {
        "total_locs": len(locs_data),
        "ending_locs_count": 0,
        "desc_chars_total": 0,
        "desc_words_total": 0,
        "locs_with_description_count": 0,
        "cyclic_loc_names": set(),
        "duplicate_loc_names_set": set(),
        "locs_without_description_names": []
    }
    for loc_obj in locs_data:
        loc_name_display = loc_obj.name if loc_obj.name else f"локация_без_имени_ID_{loc_obj.id}"
        if loc_obj.end: stats["ending_locs_count"] += 1
        
        desc_text_current = getattr(loc_obj, 'desc', "")
        if desc_text_current and desc_text_current != "Нет описания":
            stats["locs_with_description_count"] += 1
            stats["desc_chars_total"] += len(desc_text_current)
            stats["desc_words_total"] += len(desc_text_current.split())
        else:
            stats["locs_without_description_names"].append(f'"{loc_name_display}"')
        
        if getattr(loc_obj, 'cycle', False): stats["cyclic_loc_names"].add(f'"{loc_name_display}"')
        if getattr(loc_obj, 'dup', False) and loc_obj.name: stats["duplicate_loc_names_set"].add(loc_obj.name)
    return stats

def _collect_link_stats(locs_data: List[Loc]) -> Dict[str, Any]:
    stats = {
        "links_total_count": 0, "links_btn_count": 0, "links_btn_local_count": 0,
        "links_btn_menu_count": 0, "links_goto_count": 0, "links_proc_count": 0,
        "links_auto_count": 0, "phantoms_by_source_and_type": {},
        "empty_label_btns_by_source": {}, "branching_locs_data": [], 
        "target_counts": Counter(), "button_label_details_list": [], 
        "long_button_label_details": [] 
    }
    BRANCHING_THRESHOLD = 3 
    LONG_LABEL_THRESHOLD = 80

    for loc_obj in locs_data:
        loc_name_display = loc_obj.name if loc_obj.name else f"локация_без_имени_ID_{loc_obj.id}"
        current_loc_phantoms_by_type = {}
        current_loc_empty_label_btn_count = 0
        
        loc_links = getattr(loc_obj, 'links', [])
        num_outgoing_links = len(loc_links)
        if num_outgoing_links > BRANCHING_THRESHOLD:
            stats["branching_locs_data"].append((loc_name_display, num_outgoing_links))

        for link_dat in loc_links:
            if not isinstance(link_dat, tuple) or len(link_dat) < 7: 
                continue 

            t_name = link_dat[1]        
            l_type = link_dat[2]        
            link_label = link_dat[3]    
            is_ph = link_dat[4]         
            is_menu_link = link_dat[5]  
            is_local_link = link_dat[6] 

            stats["links_total_count"] += 1

            if l_type == "btn":
                stats["links_btn_count"] += 1
                if is_local_link:  stats["links_btn_local_count"] += 1
                if is_menu_link:   stats["links_btn_menu_count"] += 1
                
                if not link_label or not link_label.strip():
                    current_loc_empty_label_btn_count += 1
                else: 
                    stripped_label = link_label.strip()
                    stats["button_label_details_list"].append({
                        "length": len(stripped_label), "text": stripped_label, "source_loc": loc_name_display
                    })
                    if len(stripped_label) > LONG_LABEL_THRESHOLD:
                        stats["long_button_label_details"].append(f'"{loc_name_display}" - "{stripped_label}"')
            elif l_type == "goto": stats["links_goto_count"] += 1
            elif l_type == "proc": stats["links_proc_count"] += 1
            elif l_type == "auto": stats["links_auto_count"] += 1

            if is_ph and t_name:
                current_loc_phantoms_by_type.setdefault(l_type, []).append(t_name)
            
            if t_name and not is_ph: 
                stats["target_counts"][t_name] += 1
        
        if current_loc_phantoms_by_type:
            target_dict_main = stats["phantoms_by_source_and_type"].setdefault(loc_name_display, {})
            for ph_type, ph_targets in current_loc_phantoms_by_type.items():
                target_dict_main.setdefault(ph_type, []).extend(ph_targets)
        
        if current_loc_empty_label_btn_count > 0:
            stats["empty_label_btns_by_source"][loc_name_display] = current_loc_empty_label_btn_count
            
    return stats

# --- Вспомогательные функции для ФОРМИРОВАНИЯ СПИСКОВ СТРОК статистики (с исправлениями отступов) ---

def _join_blocks(blocks: List[List[str]]) -> List[str]:
    final_lines = []
    first_block_added = False
    for block in blocks:
        if block: 
            if first_block_added:
                final_lines.append("") 
            final_lines.extend(block)
            first_block_added = True
    return final_lines

def _format_location_stats_lines(basic_stats: Dict[str, Any], link_stats: Dict[str, Any], locs_data: List[Loc]) -> List[str]:
    blocks_for_this_section = []

    avg_desc_lines = []
    if basic_stats["locs_with_description_count"] > 0:
        avg_words = basic_stats["desc_words_total"] / basic_stats["locs_with_description_count"]
        avg_chars = basic_stats["desc_chars_total"] / basic_stats["locs_with_description_count"]
        avg_desc_lines.append(f"Средняя длина описания (для {basic_stats['locs_with_description_count']} лок.): {avg_words:.1f} слов, {avg_chars:.1f} симв.")
    if avg_desc_lines: blocks_for_this_section.append(avg_desc_lines)
    
    top_desc_lines = []
    all_description_details = []
    for loc_obj in locs_data:
        desc_text_current = getattr(loc_obj, 'desc', "")
        if desc_text_current and desc_text_current != "Нет описания":
            loc_name_display = loc_obj.name if loc_obj.name else f"локация_без_имени_ID_{loc_obj.id}"
            desc_chars_current = len(desc_text_current)
            desc_words_current = len(desc_text_current.split())
            detail_str = f'"{loc_name_display}" ({desc_words_current} слов, {desc_chars_current} симв.)'
            all_description_details.append((desc_chars_current, detail_str))

    TOP_N_DESCRIPTIONS = 5
    if all_description_details: 
        sorted_long_descriptions = sorted(all_description_details, key=lambda item: item[0], reverse=True)
        top_desc_lines.append(f"Локации с самыми большими описаниями (топ {min(TOP_N_DESCRIPTIONS, len(sorted_long_descriptions))}):")
        for _, detail_str in sorted_long_descriptions[:TOP_N_DESCRIPTIONS]:
            top_desc_lines.append(f"{detail_str}") # NO INDENT
    elif basic_stats["locs_with_description_count"] > 0 : 
        top_desc_lines.append("Локации с самыми большими описаниями: нет (недостаточно данных для топа).")
    if top_desc_lines: blocks_for_this_section.append(top_desc_lines)

    no_desc_lines = []
    if basic_stats["locs_without_description_names"]:
        no_desc_lines.append(f"Локации без описания: {len(basic_stats['locs_without_description_names'])} шт. ({', '.join(sorted(basic_stats['locs_without_description_names']))})")
    if no_desc_lines: blocks_for_this_section.append(no_desc_lines)

    branching_lines = []
    BRANCHING_LOCS_TOP_N = 5 
    BRANCHING_THRESHOLD = 3  
    if link_stats["branching_locs_data"]:
        sorted_branching_locs = sorted(link_stats["branching_locs_data"], key=lambda item: item[1], reverse=True)
        branching_lines.append(f"Локации-\"развилки\" (с >{BRANCHING_THRESHOLD} связями, топ {min(BRANCHING_LOCS_TOP_N, len(sorted_branching_locs))}):")
        for loc_name_br, link_count_br in sorted_branching_locs[:BRANCHING_LOCS_TOP_N]:
            branching_lines.append(f"\"{loc_name_br}\": {link_count_br} связей") # NO INDENT
    if branching_lines: blocks_for_this_section.append(branching_lines)
    
    popular_lines = []
    POPULAR_TARGETS_TOP_N = 5 
    if link_stats["target_counts"]:
        most_common_targets = link_stats["target_counts"].most_common(POPULAR_TARGETS_TOP_N)
        if most_common_targets: 
            popular_lines.append(f"Самые \"популярные\" локации (на которые ссылаются, топ {min(POPULAR_TARGETS_TOP_N, len(most_common_targets))}):")
            for target_name_pop, count_pop in most_common_targets:
                popular_lines.append(f"\"{target_name_pop}\": {count_pop} ссылок") # NO INDENT
    if popular_lines: blocks_for_this_section.append(popular_lines)
        
    return _join_blocks(blocks_for_this_section)

def _format_link_stats_lines(basic_stats: Dict[str, Any], link_stats: Dict[str, Any], locs_data: List[Loc]) -> List[str]:
    blocks_for_this_section = []
    
    avg_max_links_lines = []
    total_locs = basic_stats["total_locs"]
    if total_locs > 0 and link_stats["links_total_count"] > 0 : 
        avg_max_links_lines.append(f"Среднее количество связей на локацию: {link_stats['links_total_count'] / total_locs:.1f} шт.")

    max_links_count = 0
    loc_with_max_links = ""
    if total_locs > 0: 
        for l_obj_max in locs_data:
            current_links_max = len(getattr(l_obj_max, 'links', []))
            if current_links_max > max_links_count:
                max_links_count = current_links_max
                loc_with_max_links = l_obj_max.name if l_obj_max.name else f"локация_без_имени_ID_{l_obj_max.id}"
        if max_links_count > 0: 
            avg_max_links_lines.append(f"Максимальное количество связей из одной локации: {max_links_count} шт. (из \"{loc_with_max_links}\")")
    if avg_max_links_lines: blocks_for_this_section.append(avg_max_links_lines)

    link_details_lines = []
    if link_stats["links_total_count"] > 0: link_details_lines.append(f"Связей (всего): {link_stats['links_total_count']} шт.")
    if link_stats["links_btn_count"] > 0:
        btn_details_list = []
        if link_stats["links_btn_local_count"] > 0: btn_details_list.append(f"{link_stats['links_btn_local_count']} локальных")
        if link_stats["links_btn_menu_count"] > 0: btn_details_list.append(f"{link_stats['links_btn_menu_count']} меню")
        details_str_btn = f" (из них {', '.join(btn_details_list)})" if btn_details_list else ""
        link_details_lines.append(f"Кнопки (btn): {link_stats['links_btn_count']} шт.{details_str_btn}") # NO INDENT (already top level for this sub-block)

    if link_stats["links_goto_count"] > 0: link_details_lines.append(f"Переходы (goto): {link_stats['links_goto_count']} шт.") # NO INDENT
    if link_stats["links_proc_count"] > 0: link_details_lines.append(f"Процедуры (proc): {link_stats['links_proc_count']} шт.") # NO INDENT
    if link_stats["links_auto_count"] > 0: link_details_lines.append(f"Автопереходы: {link_stats['links_auto_count']} шт.") # NO INDENT
    if link_details_lines: blocks_for_this_section.append(link_details_lines)
    
    return _join_blocks(blocks_for_this_section)

def _format_problematic_stats_lines(basic_stats: Dict[str, Any], link_stats: Dict[str, Any]) -> List[str]:
    blocks_for_this_section = []

    cyclic_lines = []
    cyclic_locs_count_val = len(basic_stats["cyclic_loc_names"])
    if cyclic_locs_count_val > 0:
        sorted_cyclic_loc_names_str = ", ".join(sorted(list(basic_stats["cyclic_loc_names"])))
        cyclic_lines.append(f"Самоссылки: {cyclic_locs_count_val} шт. (в локациях: {sorted_cyclic_loc_names_str})")
    if cyclic_lines: blocks_for_this_section.append(cyclic_lines)
    
    duplicate_lines = []
    duplicate_locs_count = len(basic_stats["duplicate_loc_names_set"])
    if basic_stats["duplicate_loc_names_set"]:
        sorted_duplicate_names_str = ", ".join(f'"{name}"' for name in sorted(list(basic_stats["duplicate_loc_names_set"])))
        duplicate_lines.append(f"Дубликаты: {sorted_duplicate_names_str} ({duplicate_locs_count} шт.)")
    if duplicate_lines: blocks_for_this_section.append(duplicate_lines)

    phantom_lines = []
    if link_stats["phantoms_by_source_and_type"]:
        phantom_lines.append("Фантомные ссылки:")
        for loc_name_ph, types_dict_ph in sorted(link_stats["phantoms_by_source_and_type"].items()):
            phantom_lines.append(f"Фантомы в локации \"{loc_name_ph}\":") # NO INDENT
            for link_type_ph, targets_list_ph in sorted(types_dict_ph.items()):
                unique_sorted_targets_ph = sorted(list(set(targets_list_ph)))
                targets_str_ph = ", ".join(f'"{t}"' for t in unique_sorted_targets_ph)
                phantom_lines.append(f"{link_type_ph}: {targets_str_ph}") # NO INDENT
    else:
        phantom_lines.append("Фантомные ссылки:")
        phantom_lines.append("Фантомных ссылок не найдено.") # NO INDENT
    if phantom_lines: blocks_for_this_section.append(phantom_lines)

    empty_label_lines = []
    if link_stats["empty_label_btns_by_source"]:
        empty_label_lines.append("Кнопки (btn) с пустыми надписями:")
        for loc_name_empty, count_empty in sorted(link_stats["empty_label_btns_by_source"].items()):
            empty_label_lines.append(f"В локации \"{loc_name_empty}\": {count_empty} шт.") # NO INDENT
    if empty_label_lines: blocks_for_this_section.append(empty_label_lines)
        
    return _join_blocks(blocks_for_this_section)

def _format_button_label_analysis_lines(link_stats: Dict[str, Any]) -> List[str]:
    blocks_for_this_section = []
    button_label_details_list = link_stats.get("button_label_details_list", [])
    
    if not button_label_details_list:
        return []

    avg_len_lines = []
    all_label_lengths = [item["length"] for item in button_label_details_list]
    if all_label_lengths: 
        avg_label_len = sum(all_label_lengths) / len(all_label_lengths)
        avg_len_lines.append(f"Средняя длина: {avg_label_len:.1f} симв.") # NO INDENT
    if avg_len_lines: blocks_for_this_section.append(avg_len_lines)
    
    top_labels_lines = []
    sorted_button_details = sorted(button_label_details_list, key=lambda x: x["length"])
    if len(sorted_button_details) >= 1:
        top_labels_lines.append("Самые длинные (топ-3):") # NO INDENT
        for detail in sorted_button_details[-3:][::-1]:
            text_preview = detail['text'][:30] + "..." if len(detail['text']) > 30 else detail['text']
            top_labels_lines.append(f"{detail['length']} симв. (в \"{detail['source_loc']}\": \"{text_preview}\")") # NO INDENT

        top_labels_lines.append("Самые короткие (топ-3):") # NO INDENT
        for detail in sorted_button_details[:3]:
            top_labels_lines.append(f"{detail['length']} симв. (в \"{detail['source_loc']}\": \"{detail['text']}\")") # NO INDENT
    if top_labels_lines: blocks_for_this_section.append(top_labels_lines)
    
    very_long_labels_lines = []
    LONG_LABEL_THRESHOLD = 80 
    long_button_labels = link_stats.get("long_button_label_details", [])
    if long_button_labels:
        very_long_labels_lines.append(f"Кнопки с длиной надписи >{LONG_LABEL_THRESHOLD} символов ({len(long_button_labels)} шт.):") # NO INDENT
        for label_detail_str in long_button_labels:
            very_long_labels_lines.append(f"{label_detail_str}") # NO INDENT
    if very_long_labels_lines: blocks_for_this_section.append(very_long_labels_lines)
        
    return _join_blocks(blocks_for_this_section)


# --- Основная функция get_stats (без изменений в логике вызова) ---
def get_stats(locs_data: List[Loc]) -> str:
    if not locs_data:
        return "\n--- Статистика Квеста ---\nСписок локаций пуст. Статистика не может быть рассчитана.\n-------------------------\n"

    output_lines = ["--- Общая Статистика Квеста ---"] 

    basic_stats = _collect_basic_stats(locs_data)
    link_stats = _collect_link_stats(locs_data) 

    if basic_stats["total_locs"] > 0: output_lines.append(f"Локации: {basic_stats['total_locs']} шт.")
    if basic_stats["ending_locs_count"] > 0: output_lines.append(f"Концовки: {basic_stats['ending_locs_count']} шт.")
    if basic_stats.get("desc_chars_total", 0) > 0:
        output_lines.append(f"Символов в pln/p (всего): {basic_stats['desc_chars_total']}") 

    sections_data = [
        ("\n--- Статистика по Локациям ---", _format_location_stats_lines(basic_stats, link_stats, locs_data)),
        ("\n--- Статистика по Связям ---", _format_link_stats_lines(basic_stats, link_stats, locs_data)),
        ("\n--- Потенциальные Проблемы и Особенности ---", _format_problematic_stats_lines(basic_stats, link_stats)),
        ("\n--- Анализ надписей кнопок (для непустых) ---", _format_button_label_analysis_lines(link_stats)),
    ]

    for title, content_lines in sections_data:
        if content_lines: 
            output_lines.append(title)
            output_lines.extend(content_lines)
        
    output_lines.append("\n----------------------------------")
    return "\n".join(output_lines)

# Пример использования (для тестирования вне Sublime)
if __name__ == '__main__':
    class MockLoc:
        def __init__(self, name, id_str="mock_id", desc="Нет описания", end=False, cycle=False, dup=False, links=None):
            self.name = name
            self.id = id_str
            self.desc = desc
            self.end = end
            self.cycle = cycle
            self.dup = dup
            self.links = links if links is not None else []

    mock_locs = [
        MockLoc(name="start", desc="Это старт. Тут много текста.", links=[
            (None, "loc_a", "btn", "Кнопка А", False, False, False),
            (None, "loc_b", "btn", "Кнопка Б очень длинная надпись более 80 символов чтобы проверить порог", False, False, True), 
            (None, "популярная_цель", "btn", "к популярной", False, False, False)
        ]),
        MockLoc(name="loc_a", desc="Локация А.", links=[
            (None, "loc_c", "goto", "", False, False, False), 
            (None, "phantom_1", "btn", "", True, False, False), 
            (None, "популярная_цель", "btn", "тоже к популярной", False, False, False)
        ]),
        MockLoc(name="loc_b", desc="Локация Б.", links=[ (None, "start", "btn", "Назад на старт", False, True, False), ]),
        MockLoc(name="loc_c", desc="Локация С, тут тоже есть описание.", end=True, links=[]),
        MockLoc(name="loc_d", desc="Нет описания", cycle=True, links=[(None, "loc_d", "goto", "", False, False, False)]), 
        MockLoc(name="start", desc="Дубликат старта", dup=True, links=[(None, "loc_a", "btn", "К дубликату А", False, False, False)]),
        MockLoc(name="развилка", desc="много выходов", links=[
            (None, "t1", "btn", "1", False, False, False), (None, "t2", "btn", "2", False, False, False),
            (None, "t3", "btn", "3", False, False, False), (None, "t4", "btn", "4", False, False, False),
            (None, "t5", "btn", "5", False, False, False),
        ]),
         MockLoc(name="популярная_цель", desc="на меня много ссылаются", links=[]),
         MockLoc(name="loc_e", desc="ссылка на популярную", links=[(None, "популярная_цель", "goto", "", False, False, False)]),
         MockLoc(name="loc_f", desc="еще ссылка на популярную", links=[(None, "популярная_цель", "proc", "", False, False, False)]),
    ]
    stats_output = get_stats(mock_locs)
    print(stats_output)