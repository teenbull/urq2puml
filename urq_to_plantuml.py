import sublime
import sublime_plugin
import os
import re
# Removed: tempfile, subprocess, urllib.request, urllib.parse, base64, zlib, string

# Constants for PlantUML styling
_PLANTUML_PHANTOM_NODE_DEFINITION = """state "//phantom" as PHANTOM_NODE_URQ #ffcccb {
  PHANTOM_NODE_URQ: (Ссылка на несуществующую локацию)
}
"""
_PLANTUML_SKINPARAMS = """skinparam stateArrowColor #606060
skinparam state {
    BackgroundColor #F0F8FF
    BorderColor #A9A9A9
    FontColor #303030
    ArrowFontColor #404040
}
"""
_END_COLOR = "#d0f0d0"
_AUTO_FORMAT = "{0} -[#CD5C5C,dotted]-> {1}\n"
_PHANTOM_ARROW = "[#CD5C5C,dotted]"
_START_LOC = "[*] --> 0\n"

class UrqToPlantumlCommand(sublime_plugin.TextCommand):
    def run(self, edit): # Removed nopng parameter
        # Путь к файлу
        current_file = self.view.file_name()

        # Проверка расширения файла
        if not current_file or not current_file.lower().endswith('.qst'):
            sublime.error_message("Файл должен быть URQ (.qst)")
            return

        # Статус бар
        self.view.window().status_message("Конвертация URQ в PlantUML...")

        # Список предупреждений
        self.warnings = []

        try:
            # Парсинг файла URQ
            locations_data = self._parse_urq_file(current_file)

            # Если парсинг вернул пустые данные из-за ошибки, останавливаемся
            if not locations_data or not locations_data[0]:
                 # Сообщения об ошибках парсинга уже добавлены в self.warnings и выведены в консоль
                 return

            # Путь к выходному .puml файлу
            puml_file = os.path.splitext(current_file)[0] + '.puml'

            # Генерация PlantUML кода
            self._generate_plantuml(locations_data, puml_file) # plantuml_code variable no longer needed here

            # Открытие .puml файла
            self.view.window().open_file(puml_file)
            self.view.window().status_message("Конвертация URQ в PlantUML: .puml файл сгенерирован.")


        except Exception as e:
            # Критическая ошибка парсинга или записи PUML
            msg = "URQ to PlantUML Critical Error: Произошла ошибка при конвертации: {}".format(e)
            self.warnings.append(msg)
            print(msg)

        finally:
            # Показать все собранные предупреждения в консоль
            if self.warnings:
                 print("\n" + "="*20 + " URQ to PlantUML Warnings " + "="*20)
                 for warning in self.warnings:
                     print(warning)
                 print("="*61 + "\n")


    def _parse_urq_file(self, file_path):
        """Парсит URQ файл. Возвращает (locations, transitions, numbered_locations, auto_transitions, goto_transitions, first_location_name)."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            try:
                with open(file_path, 'r', encoding='cp1251') as f:
                    content = f.read()
            except UnicodeDecodeError:
                 msg = "URQ to PlantUML Error: Не удалось определить кодировку файла {}. Попробуйте UTF-8.".format(os.path.basename(file_path))
                 self.warnings.append(msg)
                 print(msg)
                 return ({}, [], {}, [], [], None)

        locations = {} # location_name -> description
        numbered_locations = {} # location_name -> number_alias (str)
        location_details = [] # [(name, content_start, content_end)] - для сохранения порядка

        location_marker_pattern = re.compile(r'^\s*:([^\n]+)', re.MULTILINE)
        location_matches = list(location_marker_pattern.finditer(content))

        if not location_matches:
             msg = "URQ to PlantUML Warning: В файле {} не найдено ни одной метки локации (:LocationName).".format(os.path.basename(file_path))
             self.warnings.append(msg)
             print(msg)
             return ({}, [], {}, [], [], None)

        # Pass 1: Идентификация всех локаций, их содержимого и присвоение номеров
        for i, match in enumerate(location_matches):
            name = match.group(1).strip()
            start_pos = match.end()
            end_pos = location_matches[i+1].start() if i + 1 < len(location_matches) else len(content)

            if name not in numbered_locations:
                numbered_locations[name] = str(len(numbered_locations))

            # Извлекаем описание (первый pln)
            # For pln, search in the original slice before any potential lstrip for transitions
            location_content_for_pln = content[start_pos:end_pos]
            pln_match = re.search(r'pln\s+([^.\n]+)', location_content_for_pln)
            description = pln_match.group(1).strip() if pln_match else "Нет описания"
            locations[name] = description

            location_details.append((name, start_pos, end_pos))

        first_location_name = location_details[0][0] if location_details else None
        raw_transitions = []

        # Pass 2: Идентификация переходов
        for i, (name, start_pos, end_pos) in enumerate(location_details):
            location_content_slice = content[start_pos:end_pos]
            
            # Apply lstrip to the location's content block before regex for transitions
            # This was the hypothesized fix based on user feedback
            location_content = location_content_slice.lstrip()

            has_end = re.search(r'^\s*\bend\b', location_content, re.MULTILINE | re.IGNORECASE) is not None
            # Note: has_goto_keyword check might be slightly less reliable if lstrip removed all lines before a goto
            # However, for identifying auto-transitions, it's about the *presence* of the keywords.
            has_goto_keyword_in_stripped = re.search(r'^\s*\bgoto\b', location_content, re.MULTILINE | re.IGNORECASE) is not None


            # Автоматический переход (если нет end, goto, и это не последняя локация)
            # The logic for auto-transition should ideally consider the original structure
            # before lstrip, or ensure lstrip doesn't change the "emptiness" interpretation.
            # For now, using has_end and has_goto_keyword_in_stripped on the lstrip'd content.
            if not has_end and not has_goto_keyword_in_stripped and i + 1 < len(location_details):
                 next_location_name = location_details[i+1][0]
                 raw_transitions.append((name, next_location_name, "auto", "auto"))


            btn_matches = re.finditer(r'^\s*\bbtn\s+([^,\n]+),\s*([^\n]+)', location_content, re.MULTILINE | re.IGNORECASE)
            for btn_match_obj in btn_matches:
                target_location = btn_match_obj.group(1).strip()
                button_text = btn_match_obj.group(2).strip()
                if target_location:
                    raw_transitions.append((name, target_location, button_text, "btn"))
                else:
                     msg = "URQ to PlantUML Warning: Пустая цель btn (из '{}', кнопка '{}'). Переход пропущен в парсинге.".format(name, button_text)
                     self.warnings.append(msg)
                     print(msg)

            goto_matches = re.finditer(r'^\s*\bgoto\s+(.+)', location_content, re.MULTILINE | re.IGNORECASE)
            for goto_match_obj in goto_matches:
                target_location = goto_match_obj.group(1).strip()
                if target_location:
                    raw_transitions.append((name, target_location, "goto", "goto"))
                else:
                    msg = "URQ to PlantUML Warning: Пустая цель goto (из '{}'). Переход пропущен в парсинге.".format(name)
                    self.warnings.append(msg)
                    print(msg)


        transitions = [(s, t, l) for s, t, l, type_val in raw_transitions if type_val == "btn"]
        auto_transitions = [(s, t, l) for s, t, l, type_val in raw_transitions if type_val == "auto"]
        goto_transitions = [(s, t, l) for s, t, l, type_val in raw_transitions if type_val == "goto"]

        return (locations, transitions, numbered_locations, auto_transitions, goto_transitions, first_location_name)

    def _generate_plantuml(self, locations_data, output_file):
        """Генерирует PlantUML код."""
        locations = locations_data[0]
        transitions = locations_data[1] # (source_name, target_name, label) - btn
        auto_transitions = locations_data[3] # (source_name, target_name, "auto") - auto
        goto_transitions = locations_data[4] # (source_name, target_name, "goto") - goto
        numbered_locations = locations_data[2] # location_name -> number_alias (str)

        plantuml_code = "@startuml\n"
        plantuml_code += _PLANTUML_PHANTOM_NODE_DEFINITION
        plantuml_code += _PLANTUML_SKINPARAMS

        source_locations = set()
        all_raw_transitions_for_end_loc_detection = transitions + auto_transitions + goto_transitions
        for source, _, _ in all_raw_transitions_for_end_loc_detection:
            source_locations.add(source)
        end_locations = [name for name in locations if name not in source_locations]

        sorted_location_names = sorted(numbered_locations, key=lambda k: int(numbered_locations[k]))

        for name in sorted_location_names:
             loc_number = numbered_locations[name]
             description = locations.get(name, "Нет описания")

             sanitized_name = self.sanitize_string(name, max_length=40)
             sanitized_description = self.sanitize_string(description, max_length=50)

             plantuml_code += 'state "{0}" as {1}'.format(sanitized_name, loc_number)
             if name in end_locations:
                 plantuml_code += ' {}'.format(_END_COLOR)
             plantuml_code += '\n'
             plantuml_code += '{0}: {1}\n'.format(loc_number, sanitized_description)

        if '0' in numbered_locations.values():
            plantuml_code += _START_LOC

        # btn transitions
        for source, target, label in transitions: # label is button text
            source_num = numbered_locations.get(source)
            target_num = numbered_locations.get(target)

            if source_num is not None:
                if target_num is not None:
                    sanitized_label = self.sanitize_string(label, max_length=30)
                    plantuml_code += '{0} --> {1} : {2}\n'.format(source_num, target_num, sanitized_label)
                else:
                    # Target location not found, redirect to PHANTOM_NODE_URQ
                    sanitized_phantom_label = self.sanitize_string(label, max_length=30)
                    # Apply new style using the combined style specifier
                    plantuml_code += '{0} -{1}-> PHANTOM_NODE_URQ : [{2}]\n'.format(
                        source_num, _PHANTOM_ARROW, sanitized_phantom_label)
                    msg = "URQ to PlantUML Warning: Целевая локация '{}' для btn из '{}' (метка: '{}') не найдена. Переход перенаправлен на PHANTOM_NODE_URQ.".format(target, source, label)
                    self.warnings.append(msg)
                    print(msg)
            else:
                 msg = "URQ to PlantUML Warning: Исходная локация '{}' для перехода btn к '{}' ('{}') не найдена. Переход пропущен.".format(source, target, label)
                 self.warnings.append(msg)
                 print(msg)

        # auto transitions
        for source, target, _ in auto_transitions:
            source_num = numbered_locations.get(source)
            target_num = numbered_locations.get(target)

            if source_num is not None and target_num is not None:
                 plantuml_code += _AUTO_FORMAT.format(source_num, target_num)
            else:
                 if source_num is None:
                     msg = "URQ to PlantUML Warning: Исходная локация '{}' для авто-перехода к '{}' не найдена. Переход пропущен.".format(source, target)
                 else:
                     msg = "URQ to PlantUML Warning: Целевая локация '{}' для авто-перехода из '{}' не найдена. Переход пропущен (авто).".format(target, source)
                 self.warnings.append(msg)
                 print(msg)

        # goto transitions
        for source, target, label_is_goto_keyword in goto_transitions: # label_is_goto_keyword is "goto"
            source_num = numbered_locations.get(source)
            target_num = numbered_locations.get(target)

            if source_num is not None:
                if target_num is not None:
                     plantuml_code += '{0} --> {1} : [{2}]\n'.format(source_num, target_num, label_is_goto_keyword)
                else:
                    # Target location not found, redirect to PHANTOM_NODE_URQ
                    sanitized_phantom_target_name = self.sanitize_string(target, max_length=30)
                    # Apply new style using the combined style specifier
                    plantuml_code += '{0} -{1}-> PHANTOM_NODE_URQ : [{2}]\n'.format(
                        source_num, _PHANTOM_ARROW, sanitized_phantom_target_name)
                    msg = "URQ to PlantUML Warning: Целевая локация '{}' для goto из '{}' не найдена. Переход перенаправлен на PHANTOM_NODE_URQ.".format(target, source)
                    self.warnings.append(msg)
                    print(msg)
            else:
                 msg = "URQ to PlantUML Warning: Исходная локация '{}' для перехода goto к '{}' не найдена. Переход пропущен.".format(source, target)
                 self.warnings.append(msg)
                 print(msg)

        plantuml_code += "@enduml\n"

        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(plantuml_code)
            print("URQ to PlantUML: Файл PlantUML создан: {}".format(output_file))
        except Exception as e:
             msg = "URQ to PlantUML Critical Error: Ошибка записи PlantUML файла {}: {}".format(output_file, e)
             self.warnings.append(msg)
             print(msg)
             raise Exception(msg)

    def sanitize_string(self, s, max_length=30): # Default max_length as requested for general case
        """Санитизирует строку для PlantUML: берет первую строку, обрезает, добавляет ... и экранирует символы."""
        if s is None:
            return ""

        # 1. Take only the first line
        # s = s.splitlines()[0] if s.splitlines() else ""

        # 2. Truncate if longer than max_length
        add_ellipsis = False
        if len(s) > max_length:
            s = s[:max_length]
            add_ellipsis = True

        # 3. Экранирование символов в обрезанной части
        # Экранируем обратную косую черту, затем двойную кавычку
        # This is important for PlantUML syntax if names/descriptions contain these characters.
        # sanitized_s = s.replace('\\', '\\\\').replace('"', '\\"')
        s = s.replace('\"','\'\'')

        # 4. Добавление многоточия
        if add_ellipsis:
            return s + "..."
        else:
            return s

