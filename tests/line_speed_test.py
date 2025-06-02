import re
import time

# --- Общие компоненты (скопированы из test_line_numbers.py) ---
LOC_PATTERN = re.compile(r'^\s*:([^\n]+)', re.MULTILINE)
COMMENTS_REMOVAL = re.compile(r'/\*.*?\*/|;[^\n]*', re.MULTILINE | re.DOTALL)

class TestLoc:
    def __init__(self, id, name, line):
        self.id = id
        self.name = name
        self.line = line

    def __eq__(self, other): # Для сравнения результатов
        if not isinstance(other, TestLoc):
            return NotImplemented
        return self.id == other.id and self.name == other.name and self.line == other.line

    def __repr__(self):
        return f"TestLoc(id='{self.id}', name='{self.name}', line={self.line})"

def prep_content_silent(content): # Версия без print
    content = COMMENTS_REMOVAL.sub('', content)        
    content = re.sub(r'\n\s*_', '', content)
    content = re.sub(r'"', '\'', content)
    lines = []
    for line_text in content.split('\n'):
        if re.match(r'^\s*if\b', line_text, re.IGNORECASE):
            parts = re.split(r'\b(then|else)\b', line_text, flags=re.IGNORECASE)
            lines.extend(p.lstrip() for p in parts if p.lstrip() and p.lstrip().lower() not in ('then', 'else'))
        else:
            lines.append(line_text)
    return '\n'.join(p.strip() for p in '\n'.join(lines).split('&') if p.strip())

# --- Версия 1: Неинкрементальный подсчет (из предыдущих шагов) ---
def parse_locations_only_lines1_silent(orig_content): # Версия без print
    clean_content = prep_content_silent(orig_content)
    orig_matches = list(LOC_PATTERN.finditer(orig_content))
    clean_matches = list(LOC_PATTERN.finditer(clean_content))
    
    locs = []
    if len(orig_matches) != len(clean_matches):
        # В реальном тесте скорости это можно пропустить или логировать во внешний файл
        pass # print(f"  CRITICAL WARNING (v1): Mismatch! Orig={len(orig_matches)}, Clean={len(clean_matches)}")

    for i, clean_m in enumerate(clean_matches): 
        name_from_clean = clean_m.group(1).strip() 
        real_line = -1
        if i < len(orig_matches):
            orig_m = orig_matches[i]
            pos_colon_in_match = orig_m.group(0).find(':')
            if pos_colon_in_match != -1:
                abs_pos_colon = orig_m.start() + pos_colon_in_match
                num_prev_nl = orig_content[:abs_pos_colon].count('\n')
                real_line = num_prev_nl + 1
            else: # Fallback
                num_prev_nl = orig_content[:orig_m.start()].count('\n')
                real_line = num_prev_nl + 1
                if orig_m.start() > 0 and orig_content[orig_m.start()] == '\n':
                     potential_line_content = orig_content[orig_m.start():].split('\n', 1)[0]
                     if potential_line_content.strip().startswith(':'):
                        real_line +=1
        else: # Fallback
            num_prev_nl_clean = clean_content[:clean_m.start()].count('\n')
            real_line = num_prev_nl_clean + 1
            if clean_m.start() > 0 and clean_content[clean_m.start()] == '\n':
                 potential_line_content_clean = clean_content[clean_m.start():].split('\n', 1)[0]
                 if potential_line_content_clean.strip().startswith(':'):
                    real_line +=1
        locs.append(TestLoc(str(i), name_from_clean, real_line))
    return locs

# --- Версия 2: Инкрементальный подсчет (последняя предложенная) ---
def parse_locations_only_lines2_silent(orig_content): # Версия без print
    clean_content = prep_content_silent(orig_content)
    orig_matches = list(LOC_PATTERN.finditer(orig_content))
    clean_matches = list(LOC_PATTERN.finditer(clean_content))
    locs = []
    
    if len(orig_matches) != len(clean_matches):
        # В реальном тесте скорости это можно пропустить или логировать во внешний файл
        pass # print(f"  CRITICAL WARNING (v2): Mismatch! Orig={len(orig_matches)}, Clean={len(clean_matches)}")

    cumulative_newlines_in_orig = 0
    last_colon_pos_in_orig = 0 

    for i, clean_m in enumerate(clean_matches): 
        name_from_clean = clean_m.group(1).strip() 
        real_line = -1
        if i < len(orig_matches):
            orig_m = orig_matches[i]
            pos_colon_in_match_group = orig_m.group(0).find(':')
            if pos_colon_in_match_group != -1:
                abs_pos_colon_current = orig_m.start() + pos_colon_in_match_group
                if last_colon_pos_in_orig > abs_pos_colon_current : # Should not happen with sorted matches
                    # Fallback to recalculate from start for this specific loc
                    cumulative_newlines_in_orig = orig_content[:abs_pos_colon_current].count('\n')
                else:
                    newlines_in_segment = orig_content.count('\n', last_colon_pos_in_orig, abs_pos_colon_current)
                    cumulative_newlines_in_orig += newlines_in_segment
                real_line = cumulative_newlines_in_orig + 1
                last_colon_pos_in_orig = abs_pos_colon_current
            else: # Fallback
                num_prev_nl = orig_content[:orig_m.start()].count('\n')
                real_line = num_prev_nl + 1
                if orig_m.start() > 0 and orig_content[orig_m.start()] == '\n':
                     potential_line_content = orig_content[orig_m.start():].split('\n', 1)[0]
                     if potential_line_content.strip().startswith(':'):
                        real_line +=1
                last_colon_pos_in_orig = orig_m.start() 
        else: # Fallback
            num_prev_nl_clean = clean_content[:clean_m.start()].count('\n')
            real_line = num_prev_nl_clean + 1
            if clean_m.start() > 0 and clean_content[clean_m.start()] == '\n' :
                 potential_line_content_clean = clean_content[clean_m.start():].split('\n', 1)[0]
                 if potential_line_content_clean.strip().startswith(':'):
                    real_line +=1
        locs.append(TestLoc(str(i), name_from_clean, real_line))
    return locs

# --- Тестовые данные (ТЕСТ 9) ---
TEST_CASE_9_CONTENT = """:0
/*:1
sdfsdf
*/sdfds
end

:2
:2
:2;дубликат
:2 & дубликат
здт ываыв
:новое имя локации
pln
end"""

TEST_CASE_9_EXPECTED_LINES = {
    '0': 1,
    '2': 7,          
    '2_dup': 8,      
    '2_dup2': 9,     
    '2_dup3': 10,    
    'новое имя локации': 12
}

def verify_results(locs, expected_lines_map):
    """Проверяет, соответствуют ли результаты ожидаемым."""
    if not locs: return False
    loc_name_counts = {}
    for loc_obj in locs:
        base_name = loc_obj.name
        current_occurrence = loc_name_counts.get(base_name, 0) + 1
        loc_name_counts[base_name] = current_occurrence
        
        test_key = base_name
        if current_occurrence == 2: test_key = f"{base_name}_dup"
        elif current_occurrence > 2: test_key = f"{base_name}_dup{current_occurrence-1}"
        
        expected_line = expected_lines_map.get(test_key)
        if expected_line is None or expected_line != loc_obj.line:
            # print(f"Verification FAILED for {test_key}: Expected {expected_line}, Got {loc_obj.line} (Name: {loc_obj.name})")
            return False
    return True

# --- Основная логика теста ---
if __name__ == "__main__":
    print("--- Speed Test for Line Number Parsing ---")

    # 1. Проверка корректности один раз
    print("\n1. Verifying correctness of both functions on TEST 9:")
    
    # Используем "шумные" версии для первоначальной проверки, если нужно отладить их
    # locs_v1_check = parse_locations_only_lines1(TEST_CASE_9_CONTENT) # Предполагаем, что есть "шумная" версия
    # locs_v2_check = parse_locations_only_lines2(TEST_CASE_9_CONTENT) # Предполагаем, что есть "шумная" версия
    
    # Для теста скорости используем _silent версии
    locs_v1_check = parse_locations_only_lines1_silent(TEST_CASE_9_CONTENT)
    is_v1_correct = verify_results(locs_v1_check, TEST_CASE_9_EXPECTED_LINES)
    print(f"  parse_locations_only_lines1_silent is correct: {is_v1_correct}")
    if not is_v1_correct:
        print("    Details for v1 failure:")
        # (можно добавить вывод locs_v1_check для отладки, если нужно)


    locs_v2_check = parse_locations_only_lines2_silent(TEST_CASE_9_CONTENT)
    is_v2_correct = verify_results(locs_v2_check, TEST_CASE_9_EXPECTED_LINES)
    print(f"  parse_locations_only_lines2_silent is correct: {is_v2_correct}")
    if not is_v2_correct:
        print("    Details for v2 failure:")
        # (можно добавить вывод locs_v2_check для отладки, если нужно)

    if not (is_v1_correct and is_v2_correct):
        print("  ERROR: One or both functions are not producing correct results. Speed test might be misleading.")
        # exit() # Можно раскомментировать, чтобы остановить тест, если есть ошибки корректности

    # 2. Замер производительности
    num_runs = 1000
    print(f"\n2. Measuring performance over {num_runs} runs (TEST 9):")

    # Замер для v1
    start_time_v1 = time.perf_counter()
    for _ in range(num_runs):
        parse_locations_only_lines1_silent(TEST_CASE_9_CONTENT)
    end_time_v1 = time.perf_counter()
    time_v1 = end_time_v1 - start_time_v1
    print(f"  Time for parse_locations_only_lines1_silent: {time_v1:.4f} seconds")

    # Замер для v2
    start_time_v2 = time.perf_counter()
    for _ in range(num_runs):
        parse_locations_only_lines2_silent(TEST_CASE_9_CONTENT)
    end_time_v2 = time.perf_counter()
    time_v2 = end_time_v2 - start_time_v2
    print(f"  Time for parse_locations_only_lines2_silent: {time_v2:.4f} seconds")

    # Сравнение
    if time_v1 < time_v2:
        print(f"\n  Conclusion: parse_locations_only_lines1_silent is faster by {time_v2 - time_v1:.4f}s ({((time_v2 - time_v1)/time_v2)*100:.2f}%).")
    elif time_v2 < time_v1:
        print(f"\n  Conclusion: parse_locations_only_lines2_silent is faster by {time_v1 - time_v2:.4f}s ({((time_v1 - time_v2)/time_v1)*100:.2f}%).")
    else:
        print("\n  Conclusion: Both functions have similar performance.")