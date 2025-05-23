# Конвертер из URQ в граф PlantUML

# Путь к jar файлу с https://plantuml.com/ru/download
# Если файл не найдет - будет попытка генерить граф онлайн

PLANTUML_JAR_PATH = "C:\\java\\plantuml-1.2025.2.jar"

import sublime
import sublime_plugin
import os, sys
import subprocess
import importlib

modules_to_reload = [
    'URQ_to_PUML.urq_parser',
    'URQ_to_PUML.plantuml_gen'
]

for module_name in modules_to_reload:
    if module_name in sys.modules:
        importlib.reload(sys.modules[module_name])

# Then your imports
from .urq_parser import UrqParser
from .plantuml_gen import PlantumlGen

# Относительные импорты для Sublime Text
try:
    from .urq_parser import UrqParser
    from .plantuml_gen import PlantumlGen
except ImportError:
    from urq_parser import UrqParser
    from plantuml_gen import PlantumlGen

class UrqToPlantumlCommand(sublime_plugin.TextCommand):
    """Основная команда плагина"""
    def run(self, edit, png=False, svg=False, net=False):
        current_file = self.view.file_name()

        if not current_file:
            sublime.error_message("Нет активного файла")
            return

        is_puml = current_file.lower().endswith('.puml')
        is_qst = current_file.lower().endswith('.qst')

        if not is_puml and not is_qst:
            sublime.error_message("Файл должен быть URQ (.qst) или PlantUML (.puml)")
            return

        # Автопереключение на сетевой режим если jar потерялся
        if not net and not os.path.exists(PLANTUML_JAR_PATH):
            net = True
            print("URQ to PlantUML: JAR не найден, переключение на сетевой режим")

        self.view.window().status_message("Обработка {}...".format("PUML" if is_puml else "URQ"))
        self.warnings = []

        try:
            if is_puml:
                # Работаем с готовым PUML файлом
                puml_file = current_file
                try:
                    with open(puml_file, 'r', encoding='utf-8') as f:
                        puml_content = f.read()
                except Exception as e:
                    self._add_warning("Ошибка чтения PUML файла: {}".format(e))
                    return
                gen = PlantumlGen(PLANTUML_JAR_PATH if not net else None)
                self.warnings.extend(gen.get_warnings())
            else:
                # Парсим URQ файл
                parser = UrqParser()
                result = parser.parse_file(current_file)
                if not result:
                    self.warnings.extend(parser.get_warnings())
                    return
                
                locs, all_locs, btn_links, auto_links, goto_links, proc_links, cycle_ids = result
                self.warnings.extend(parser.get_warnings())

                # Генерируем PlantUML
                puml_file = os.path.splitext(current_file)[0] + '.puml'
                gen = PlantumlGen(PLANTUML_JAR_PATH if not net else None)
                puml_content = gen.generate_puml(locs, all_locs, btn_links, auto_links, goto_links, proc_links, cycle_ids, puml_file)
                self.warnings.extend(gen.get_warnings())
            
            if os.path.exists(puml_file):
                # !!! не открывать лишний раз puml файл
                if not png and not svg and not is_puml:
                    self.view.window().open_file(puml_file)
                
                status_parts = ["{}: {}".format(
                    "PUML обработка" if is_puml else "Конвертация URQ в PlantUML",
                    "готов" if is_puml else ".puml файл сгенерирован"
                )]
                
                # Генерируем PNG если нужно
                if png:
                    if net:
                        png_success = gen.generate_online(puml_content, puml_file, 'png')
                    else:
                        png_success = gen.generate_local(puml_file, 'png')
                    
                    if png_success:
                        status_parts.append(".png файл создан" + (" онлайн" if net else "") + " и открыт")
                        png_file = os.path.splitext(puml_file)[0] + '.png'
                        if not self._open_file_in_default_program(png_file):
                            sublime.error_message("Не удалось открыть PNG файл в программе по умолчанию")
                    else:
                        status_parts.append(".png не создан (см. предупреждения)")
                
                # Генерируем SVG если нужно
                if svg:
                    if net:
                        svg_success = gen.generate_online(puml_content, puml_file, 'svg')
                    else:
                        svg_success = gen.generate_local(puml_file, 'svg')
                    
                    if svg_success:
                        status_parts.append(".svg файл создан" + (" онлайн" if net else ""))
                        
                        svg_file_path = os.path.splitext(puml_file)[0] + '.svg'
                        if not self._open_file_in_default_program(svg_file_path):
                            sublime.error_message("Не удалось открыть SVG файл в программе по умолчанию")
                    else:
                        status_parts.append(".svg не создан (см. предупреждения)")

                self.view.window().status_message(". ".join(status_parts) + ".")
                self.warnings.extend(gen.get_warnings())
            else:
                msg = "URQ to PlantUML Error: Файл .puml не был создан."
                self.warnings.append(msg)
                print(msg)

        except Exception as e:
            self._add_warning("Critical Error: Произошла ошибка при конвертации: {}".format(e))
        finally:
            self._print_warnings()

    def _open_file_in_default_program(self, file_path):
        """Открывает файл в программе по умолчанию"""
        try:
            if sys.platform.startswith('win'):
                # Windows
                os.startfile(file_path)
            elif sys.platform.startswith('darwin'):
                # macOS
                subprocess.call(['open', file_path])
            else:
                # Linux
                subprocess.call(['xdg-open', file_path])
            return True
        except Exception as e:
            self._add_warning("Не удалось открыть файл {}: {}".format(file_path, e))
            return False

    def _add_warning(self, message):
        """Добавляет предупреждение в список"""
        full_msg = "URQ to PlantUML Warning: {}".format(message)
        self.warnings.append(full_msg)
        print(full_msg)

    def _print_warnings(self):
        """Выводит все накопленные предупреждения"""
        if self.warnings:
            print("\n" + "=" * 20 + " URQ to PlantUML Warnings " + "=" * 20)
            for warning in self.warnings:
                print(warning)
            print("=" * 61 + "\n")