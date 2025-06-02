# -*- coding: utf-8 -*-
# test_line_numbers.py
# Тестируем правильность номеров строк для локаций

import re
import os

# Копируем нужные регексы из оригинала
LOC_PATTERN = re.compile(r'^\s*:([^\n]+)', re.MULTILINE)
COMMENTS_REMOVAL = re.compile(r'/\*.*?\*/|;[^\n]*', re.MULTILINE | re.DOTALL)

class TestLoc:
    """Упрощенный класс Loc для целей тестирования номеров строк."""
    def __init__(self, id, name, line):
        self.id = id
        self.name = name
        self.line = line
        self.desc = "Test Description" 
        self.dup = False
        self.cycle = False
        self.end = False
        self.non_end = False
        self.tech = False 
        self.orphan = False
        self.links = []
        self.vars = set()
        self.invs = set()

    def _is_tech_loc(self, name):
        return False

def prep_content(content):
    """Приведенная к соответствию с основным парсером версия _prep_content."""
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

def parse_locations_only_lines2(orig_content):
    """
    Парсит локации с оптимизированным инкрементальным подсчетом номеров строк.
    """
    clean_content = prep_content(orig_content) # prep_content остается как есть
    
    orig_matches = list(LOC_PATTERN.finditer(orig_content))
    clean_matches = list(LOC_PATTERN.finditer(clean_content))
        
    if len(orig_matches) != len(clean_matches): 
        print(f"  CRITICAL WARNING: Mismatch in loc counts! Orig={len(orig_matches)}, Clean={len(clean_matches)}")
        # Можно добавить более детальный вывод расхождений, если это происходит

    locs = []
    
    # Инициализация для инкрементального подсчета в orig_content
    cumulative_newlines_in_orig = 0
    last_colon_pos_in_orig = 0 # Позиция двоеточия предыдущей метки в orig_content

    for i, clean_m in enumerate(clean_matches): 
        name_from_clean = clean_m.group(1).strip() 
        real_line = -1
        
        if i < len(orig_matches):
            orig_m = orig_matches[i]
            
            pos_colon_in_match_group = orig_m.group(0).find(':')
            
            if pos_colon_in_match_group != -1:
                # Абсолютная позиция двоеточия текущей метки в orig_content
                abs_pos_colon_current = orig_m.start() + pos_colon_in_match_group
                
                # Считаем '\n' только в сегменте от двоеточия предыдущей метки
                # до двоеточия текущей метки.
                # Убедимся, что start_count_pos не больше end_count_pos
                start_count_pos = min(last_colon_pos_in_orig, abs_pos_colon_current)
                end_count_pos = max(last_colon_pos_in_orig, abs_pos_colon_current)

                if last_colon_pos_in_orig > abs_pos_colon_current:
                    # Этого не должно происходить, если метки идут строго по порядку
                    # и мы правильно обновляем last_colon_pos_in_orig.
                    # Это может означать проблему с порядком matches или логикой.
                    # В таком случае, для безопасности, пересчитаем от начала.
                    print(f"  WARNING: Potential order issue or logic error. Recalculating newlines from start for {name_from_clean}.")
                    cumulative_newlines_in_orig = orig_content[:abs_pos_colon_current].count('\n')
                else:
                    newlines_in_segment = orig_content.count('\n', last_colon_pos_in_orig, abs_pos_colon_current)
                    cumulative_newlines_in_orig += newlines_in_segment
                
                real_line = cumulative_newlines_in_orig + 1
                
                # Обновляем позицию последнего обработанного двоеточия
                last_colon_pos_in_orig = abs_pos_colon_current
            else:
                # Fallback: двоеточие не найдено в group(0) - крайне маловероятно
                print(f"  WARNING: Colon not found in orig_match.group(0) for '{name_from_clean}'. Fallback to m.start().")
                # Используем старый, менее точный, но более простой инкрементальный метод по m.start()
                # Здесь нужна своя пара cumulative_newlines_fallback / last_fallback_pos, если смешивать
                # Проще всего для fallback посчитать от начала файла до m.start()
                newlines_before_match_start = orig_content[:orig_m.start()].count('\n')
                real_line = newlines_before_match_start + 1
                if orig_content[orig_m.start()] == '\n' and orig_m.start() > 0:
                     potential_line_content = orig_content[orig_m.start():].split('\n', 1)[0]
                     if potential_line_content.strip().startswith(':'):
                        real_line +=1
                last_colon_pos_in_orig = orig_m.start() # Неидеально, но fallback

        else: 
            print(f"  WARNING: No corresponding original match for clean_match '{name_from_clean}' at index {i}.")
            # Fallback для clean_content (как и раньше)
            # Этот блок тоже может использовать свой инкрементальный подсчет для clean_content, если нужно
            num_prev_nl_clean = clean_content[:clean_m.start()].count('\n') # Простой подсчет от начала clean_content
            real_line = num_prev_nl_clean + 1
            if clean_m.start() > 0 and clean_content[clean_m.start()-1] == '\n' and clean_content[clean_m.start()] != '\n': # более точная проверка
                 pass # Уже должно быть учтено в num_prev_nl_clean
            elif clean_m.start() > 0 and clean_content[clean_m.start()] == '\n' : # если сама метка начинается с \n в clean
                 potential_line_content_clean = clean_content[clean_m.start():].split('\n', 1)[0]
                 if potential_line_content_clean.strip().startswith(':'):
                    real_line +=1


        loc = TestLoc(str(i), name_from_clean, real_line)
        locs.append(loc)
    
    return locs

def parse_locations_only_lines(orig_content):
    """
    Парсит локации, фокусируясь только на правильности номеров строк,
    используя оригинальный и очищенный контент.
    """
    clean_content = prep_content(orig_content) # prep_content остается как в последнем успешном тесте
    
    orig_matches = list(LOC_PATTERN.finditer(orig_content))
    clean_matches = list(LOC_PATTERN.finditer(clean_content))
        
    if len(orig_matches) != len(clean_matches): 
        print(f"  CRITICAL WARNING: Mismatch in loc counts! Orig={len(orig_matches)}, Clean={len(clean_matches)}")

    locs = []
    # Для этого метода подсчета нам не нужен инкрементальный orig_cum_nl/orig_last_nl_pos
    # Мы будем считать для каждого match заново от начала orig_content до позиции двоеточия.

    for i, clean_m in enumerate(clean_matches): 
        name_from_clean = clean_m.group(1).strip() 
        real_line = -1
        
        if i < len(orig_matches):
            orig_m = orig_matches[i]
            
            # Находим позицию символа ':' внутри найденного полного совпадения orig_m.group(0)
            # и добавляем к начальной позиции всего совпадения orig_m.start()
            # Это дает абсолютную позицию ':' в оригинальном контенте.
            # Если ':' не найден (что маловероятно для LOC_PATTERN), то pos_colon_in_match будет -1.
            pos_colon_in_match = orig_m.group(0).find(':')
            
            if pos_colon_in_match != -1:
                abs_pos_colon = orig_m.start() + pos_colon_in_match
                # Считаем количество '\n' в оригинальном контенте до этой абсолютной позиции ':'
                num_prev_nl = orig_content[:abs_pos_colon].count('\n')
                real_line = num_prev_nl + 1
            else:
                # Fallback или ошибка: двоеточие не найдено в group(0), используем старый метод
                # Этого не должно происходить с текущим LOC_PATTERN
                print(f"  WARNING: Colon not found in orig_match.group(0) for '{name_from_clean}'. Using m.start().")
                num_prev_nl = orig_content[:orig_m.start()].count('\n')
                real_line = num_prev_nl + 1
                # Дополнительная коррекция, если m.start() указывает на \n
                if orig_content[orig_m.start()] == '\n' and orig_m.start() > 0:
                     # Если регулярка захватила \n в начале строки метки, и это не первая строка файла
                     potential_line_content = orig_content[orig_m.start():].split('\n', 1)[0]
                     if potential_line_content.strip().startswith(':'): # Убедимся, что это действительно строка с меткой
                        real_line +=1


        else: # Fallback, если clean_matches длиннее orig_matches
            print(f"  WARNING: No corresponding original match for clean_match '{name_from_clean}' at index {i}.")
            # Используем позицию clean_m в clean_content (менее точно)
            num_prev_nl_clean = clean_content[:clean_m.start()].count('\n')
            real_line = num_prev_nl_clean + 1
            # Аналогичная коррекция для clean_content
            if clean_content[clean_m.start()] == '\n' and clean_m.start() > 0:
                 potential_line_content_clean = clean_content[clean_m.start():].split('\n', 1)[0]
                 if potential_line_content_clean.strip().startswith(':'):
                    real_line +=1


        loc = TestLoc(str(i), name_from_clean, real_line)
        locs.append(loc)
    
    return locs

# --- Тестовые случаи ---
TEST_CASES = [
    {
        'name': 'Простой случай без комментариев',
        'content': ''':start
pln Начало игры
:next_loc
pln Следующая локация'''
        , 'expected_lines': {'start': 1, 'next_loc': 3}
    },
    {
        'name': 'С однострочными комментариями',
        'content': ''':begin ; это начало
pln Старт
:middle_loc ; середина истории
pln Середина
:end_loc ; конец истории'''
        , 'expected_lines': {'begin': 1, 'middle_loc': 3, 'end_loc': 5}
    },
    {
        'name': 'С многострочными комментариями',
        'content': ''':intro
/*
  Это многострочный
  комментарий к введению.
*/
pln Введение
:chapter1
  /* Еще один
     комментарий */
pln Первая глава'''
        , 'expected_lines': {'intro': 1, 'chapter1': 7}
    },
    {
        'name': 'Смешанные комментарии и пустые строки',
        'content': ''':start

; Начало
/*
  Первый блок
*/
:game_start

pln Привет
  ; Текст
/* Второй
   блок
*/
:end_game'''
        , 'expected_lines': {'start': 1, 'game_start': 7, 'end_game': 14}
    },
    {
        'name': 'С if-then-else и &',
        'content': ''':entry
if x=1 then pln One else pln Not one &
var=1 ; Set var
:outcome
pln Result'''
        , 'expected_lines': {'entry': 1, 'outcome': 4}
    },
    { 
        'name': 'Дубликаты меток (проверим, что первый получит правильный номер)',
        'content': ''':loc1
pln First instance
:loc2
pln Another
:loc1 ; Duplicate
pln Third instance'''
        , 'expected_lines': {'loc1': 1, 'loc2': 3, 'loc1_dup': 5} 
    },
    {
        'name': 'Метка сразу после комментария',
        'content': '''/* Комментарий в начале файла */
:start
pln Текст
:next
; Комментарий
:final'''
        , 'expected_lines': {'start': 2, 'next': 4, 'final': 6}
    },
    {
        'name': 'Символ подчеркивания в конце строки (для переноса)',
        'content': ''':one
pln первая_строка_текста_с_продолжением_
  и_второй_строкой
:two
pln еще_один_тест'''
        , 'expected_lines': {'one': 1, 'two': 4}
    },
    { 
            'name': 'Сложные комментарии, дубликаты, & в строке метки',
            'content': """:0
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
end""",
            'expected_lines': {
                '0': 1,
                '2': 7,          
                '2_dup': 8,      
                '2_dup2': 9,     
                '2_dup3': 10,    
                'новое имя локации': 12
            }
    }
]

def run_tests():
    print("===================================================")
    print("          ЗАПУСК ЮНИТ-ТЕСТОВ: НОМЕРА СТРОК         ")
    print("===================================================")

    total_tests = len(TEST_CASES)
    all_tests_passed_global = True

    for test_idx, test in enumerate(TEST_CASES, 1):
        print(f"\n{'-'*60}")
        print(f"ТЕСТ {test_idx}/{total_tests}: {test['name']}")
        print(f"{'-'*60}")
        
        print("\nОРИГИНАЛЬНЫЙ КОНТЕНТ:") # ВОССТАНОВЛЕНО
        for line_num, line in enumerate(test['content'].split('\n'), 1):
            print(f"{line_num:3}: {line}")
        
        print("\nОЧИЩЕННЫЙ КОНТЕНТ (для информации):") # ВОССТАНОВЛЕНО
        clean_c_debug = prep_content(test['content']) 
        for line_num, line in enumerate(clean_c_debug.split('\n'), 1):
            print(f"{line_num:3}: {line}")

        print("\nРЕЗУЛЬТАТЫ ПАРСИНГА (список локаций):")
        locs = parse_locations_only_lines(test['content'])
        # Дополнительный вывод из parse_locations_only_lines теперь сокращен, основной здесь
        print(f"  (Найдено меток в parse_locations_only_lines: {len(list(LOC_PATTERN.finditer(test['content'])))} ориг., {len(list(LOC_PATTERN.finditer(prep_content(test['content']))))} чист.)")
        for loc_obj_print in locs:
             print(f"  Loc[ID={loc_obj_print.id}, Name='{loc_obj_print.name}'] @ реальная строка {loc_obj_print.line}")


        print("\nПРОВЕРКА ОЖИДАЕМЫХ НОМЕРОВ СТРОК:")
        current_test_passed = True
        loc_name_counts_for_key_gen = {} 

        for loc_obj in locs: 
            base_name = loc_obj.name 
            
            current_occurrence_count = loc_name_counts_for_key_gen.get(base_name, 0) + 1
            loc_name_counts_for_key_gen[base_name] = current_occurrence_count
            
            test_key_for_expected: str
            if current_occurrence_count == 1:
                test_key_for_expected = base_name
            elif current_occurrence_count == 2:
                test_key_for_expected = f"{base_name}_dup" 
            else: 
                test_key_for_expected = f"{base_name}_dup{current_occurrence_count-1}" 
            
            expected_line = test['expected_lines'].get(test_key_for_expected)
            
            if expected_line is None:
                status = f"ОШИБКА: Ключ '{test_key_for_expected}' не найден в expected_lines!"
                current_test_passed = False
            elif expected_line == loc_obj.line:
                status = "ОК"
            else:
                status = f"ОШИБКА (ожидалось {expected_line}, получено {loc_obj.line})"
                current_test_passed = False
            
            print(f"  Loc[Name='{loc_obj.name}', ID='{loc_obj.id}', TestKey='{test_key_for_expected}']: найдена строка {loc_obj.line} -> {status}")
            
        print(f"\nРЕЗУЛЬТАТ ТЕСТА '{test['name']}': {'Пройден' if current_test_passed else 'НЕ ПРОЙДЕН'}")
        if not current_test_passed:
            all_tests_passed_global = False
    
    print(f"\n{'+'*60}")
    print(f"ОБЩИЙ РЕЗУЛЬТАТ ВСЕХ ТЕСТОВ: {'ВСЕ ПРОЙДЕНЫ' if all_tests_passed_global else 'ЕСТЬ ОШИБКИ'}")
    print(f"{'+'*60}")


if __name__ == "__main__":
    run_tests()

