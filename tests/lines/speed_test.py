# line_test_speed.py
import timeit
from line_parsers import (
    TestLoc, 
    parse_locations_only_lines1_silent, 
    parse_locations_only_lines2_silent,
    parse_locations_only_lines3_silent
)

# Ваш новый тестовый контент
TEST_CASE_9_CONTENT = """/* comment */:new;comment
:new;comment
p/* comment*/l/* _ sdfsd */n hello, world ; and thanks for all the fish!
/*
*/
;pln new line
pln hi!
end/*
*/
:ne
_w_loc/*sdfsf */
proc 
_old_loc
end
:000
gotoloc1
goto loc2
if a = 10 then b = 40 & if z = 5 and b = 10 then goto z else goto hell
end"""

# Сначала запустим все функции чтобы увидеть реальные результаты
def debug_all_functions():
    print("=== DEBUG: Actual results from all functions ===")
    
    funcs = [
        ("v1", parse_locations_only_lines1_silent),
        ("v2", parse_locations_only_lines2_silent), 
        ("v3", parse_locations_only_lines3_silent)
    ]
    
    for name, func in funcs:
        print(f"\n{name} results:")
        try:
            locs = func(TEST_CASE_9_CONTENT)
            for loc in locs:
                print(f"  {loc}")
        except Exception as e:
            print(f"  ERROR: {e}")
    print("=" * 50)

# Обновленные ожидаемые результаты (нужно будет скорректировать после debug)
TEST_CASE_9_EXPECTED_LINES = {
    'new': 1,           # первый :new должен быть в строке 1
    'new': 2,           # второй :new должен быть в строке 1
    'new_loc': 10,     # :ne*w*loc примерно в строке 10
    '000': 15           # :000 примерно в строке 15
}

def verify_results(locs, expected_lines_map, func_name_for_debug=""):
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
        if expected_line is None:
            print(f"    No expected line for key '{test_key}' (from loc name '{loc_obj.name}')")
            continue
        if expected_line != loc_obj.line:
            print(f"    VERIFICATION FAILED ({func_name_for_debug}) for Loc Name '{loc_obj.name}' (TestKey '{test_key}'): Expected {expected_line}, Got {loc_obj.line}")
            return False
    return True

if __name__ == "__main__":
    print("--- Speed Test for Line Number Parsing using timeit ---")
    
    # Сначала покажем что реально получается
    debug_all_functions()

    # 1. Проверка корректности один раз
    print("\n1. Verifying correctness of all functions on TEST 9:")
    
    locs_v1_check = parse_locations_only_lines1_silent(TEST_CASE_9_CONTENT)
    is_v1_correct = verify_results(locs_v1_check, TEST_CASE_9_EXPECTED_LINES, "v1_check")
    print(f"  parse_locations_only_lines1_silent is correct: {is_v1_correct}")

    locs_v2_check = parse_locations_only_lines2_silent(TEST_CASE_9_CONTENT)
    is_v2_correct = verify_results(locs_v2_check, TEST_CASE_9_EXPECTED_LINES, "v2_check")
    print(f"  parse_locations_only_lines2_silent is correct: {is_v2_correct}")
    
    locs_v3_check = parse_locations_only_lines3_silent(TEST_CASE_9_CONTENT)
    is_v3_correct = verify_results(locs_v3_check, TEST_CASE_9_EXPECTED_LINES, "v3_check")
    print(f"  parse_locations_only_lines3_silent is correct: {is_v3_correct}")

    if not (is_v1_correct and is_v2_correct and is_v3_correct):
        print("  WARNING: Some functions are not producing expected results. Update TEST_CASE_9_EXPECTED_LINES based on debug output above.")

    # 2. Замер производительности с помощью timeit
    num_executions = 1000
    num_repeats = 5

    print(f"\n2. Measuring performance using timeit (executions={num_executions}, repeats={num_repeats}):")

    # Настройка для timeit
    setup_code = """
from line_parsers import parse_locations_only_lines1_silent, parse_locations_only_lines2_silent, parse_locations_only_lines3_silent
TEST_CASE_9_CONTENT = '''""" + TEST_CASE_9_CONTENT + """'''
    """

    # Замер для v1
    stmt_v1 = "parse_locations_only_lines1_silent(TEST_CASE_9_CONTENT)"
    times_v1 = timeit.repeat(stmt=stmt_v1, setup=setup_code, number=num_executions, repeat=num_repeats)
    time_v1_best = min(times_v1)
    print(f"  Best time for parse_locations_only_lines1_silent ({num_executions} calls): {time_v1_best:.4f} seconds")

    # Замер для v2
    stmt_v2 = "parse_locations_only_lines2_silent(TEST_CASE_9_CONTENT)"
    times_v2 = timeit.repeat(stmt=stmt_v2, setup=setup_code, number=num_executions, repeat=num_repeats)
    time_v2_best = min(times_v2)
    print(f"  Best time for parse_locations_only_lines2_silent ({num_executions} calls): {time_v2_best:.4f} seconds")

    # Замер для v3
    stmt_v3 = "parse_locations_only_lines3_silent(TEST_CASE_9_CONTENT)"
    times_v3 = timeit.repeat(stmt=stmt_v3, setup=setup_code, number=num_executions, repeat=num_repeats)
    time_v3_best = min(times_v3)
    print(f"  Best time for parse_locations_only_lines3_silent ({num_executions} calls): {time_v3_best:.4f} seconds")

    # Сравнение всех трех
    times_all = [
        ("v1", time_v1_best),
        ("v2", time_v2_best), 
        ("v3", time_v3_best)
    ]
    times_all.sort(key=lambda x: x[1])
    
    print(f"\n3. Performance ranking (fastest to slowest):")
    for i, (name, time_val) in enumerate(times_all):
        if i == 0:
            print(f"  1. {name}: {time_val:.4f}s (fastest)")
        else:
            diff_abs = time_val - times_all[0][1]
            diff_perc = (diff_abs / time_val) * 100 if time_val > 0 else 0
            print(f"  {i+1}. {name}: {time_val:.4f}s (+{diff_abs:.4f}s, {diff_perc:.1f}% slower)")