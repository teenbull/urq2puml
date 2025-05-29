# urq2puml.py
# Конвертер из URQ в граф PlantUML

# ----------------------------------------------------------------------
# Путь к jar файлу с https://plantuml.com/ru/download                  #
# Если файл не найдет - будет попытка генерить граф онлайн             #
PUML_JAR_PATH = "C:\\java\\plantuml-1.2025.2.jar"                      #
# ----------------------------------------------------------------------
 
import sublime
import sublime_plugin
import os, sys
import subprocess
import importlib
import threading
import time

modules_to_reload = [
    'URQ2PUML.urq_parser',
    'URQ2PUML.puml_gen',
    'URQ2PUML.stats',
]

for module_name in modules_to_reload:
    if module_name in sys.modules:
        importlib.reload(sys.modules[module_name])

# Относительные импорты для Sublime Text
try:
    from .urq_parser import UrqParser
    from .puml_gen import PlantumlGen
    from .stats import get_stats
except ImportError:
    from urq_parser import UrqParser
    from puml_gen import PlantumlGen
    from .stats import get_stats

class UrqToPlantumlCommand(sublime_plugin.TextCommand):
    """Основная команда плагина"""
    def run(self, edit, png=False, svg=False, net=False, stats=False):
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
        if not net and not self.jar_exists():
            net = True
            print("URQ to PlantUML: JAR не найден, переключение на сетевой режим")

        self.view.window().status_message(f"Обработка {'PUML' if is_puml else 'URQ'}...")
        self.warnings = []

        try:
            if is_puml:
                # Работаем с готовым PUML файлом
                puml_file = current_file
                try:
                    with open(puml_file, 'r', encoding='utf-8') as f:
                        puml_content = f.read()
                except Exception as e:
                    self._add_warning(f"Ошибка чтения PUML файла: {e}")
                    return
                gen = PlantumlGen(PUML_JAR_PATH if not net else None)
                self.warnings.extend(gen.get_warnings())
            else:
                # Парсим URQ файл
                parser = UrqParser()
                result = parser.parse_file(current_file)
                if not result:
                    self.warnings.extend(parser.get_warnings())
                    return
                                
                self.warnings.extend(parser.get_warnings())

                # --- Вывод статистики, если флаг stats установлен ---
                if stats:
                    stats_text = get_stats(result) 

                    if stats_text:
                        stats_view = self.view.window().new_file()
                        stats_view.set_name(f"{os.path.basename(current_file)} - Статистика.md")
                        stats_view.set_scratch(True)

                        stats_text_for_view = stats_text.replace('\r\n', '\n').replace('\r', '\n')
                        stats_view.run_command('insert_text', {'text': stats_text_for_view})

                        stats_view.set_syntax_file("Packages/Markdown/Markdown.sublime-syntax")

                        self.view.window().status_message(f"Статистика для {os.path.basename(current_file)} отображена.")
                    else:
                        self._add_warning("Не удалось сгенерировать текст статистики (пустая строка).")
                    
                    # Если ТОЛЬКО статистика, то выходим после ее отображения
                    if not png and not svg:
                        self._print_warnings()
                        return 

                # Генерируем PlantUML
                puml_file = os.path.splitext(current_file)[0] + '.puml'
                gen = PlantumlGen(PUML_JAR_PATH if not net else None)
                puml_content = gen.generate_puml(result, puml_file)
                self.warnings.extend(gen.get_warnings())

                
            if os.path.exists(puml_file):
                # Не открывать лишний раз puml файл
                if not png and not svg and not is_puml:
                    self.view.window().open_file(puml_file)
                
                status_msg = f"{'PUML обработка' if is_puml else 'Конвертация URQ в PlantUML'}: {'готов' if is_puml else '.puml файл сгенерирован'}"
                
                # Генерируем PNG/SVG в фоне если нужно
                if png or svg:
                    thread = threading.Thread(target=self._gen_imgs, args=(gen, puml_content, puml_file, png, svg, net))
                    thread.daemon = True
                    thread.start()
                    
                    # Показываем прогресс
                    self._show_progress(thread)
                else:
                    self.view.window().status_message(status_msg + ".")

                self.warnings.extend(gen.get_warnings())
            else:
                self._add_warning("Critical Error: Файл .puml не был создан.")

        except Exception as e:
            self._add_warning(f"Critical Error: Произошла ошибка при конвертации: {e}")
        finally:
            self._print_warnings()

    def _gen_imgs(self, gen, puml_content, puml_file, png, svg, net):
        """Генерит изображения в отдельном потоке"""
        results = []
        
        if png:
            success = gen.generate_online(puml_content, puml_file, 'png') if net else gen.generate_local(puml_file, 'png')
            results.append(('png', success))
            
        if svg:
            success = gen.generate_online(puml_content, puml_file, 'svg') if net else gen.generate_local(puml_file, 'svg')
            results.append(('svg', success))
            
        # Обновляем UI в главном потоке
        sublime.set_timeout(lambda: self._handle_img_results(results, puml_file), 0)

    def _handle_img_results(self, results, puml_file):
        """Обрабатывает результаты генерации в главном потоке"""
        status_parts = []
        
        for fmt, success in results:
            if success:
                status_parts.append(f".{fmt} создан{' онлайн' if hasattr(self, '_net_mode') else ''} и открыт")
                img_file = f"{os.path.splitext(puml_file)[0]}.{fmt}"
                if not self._open_file_in_default_program(img_file):
                    sublime.error_message(f"Не удалось открыть {fmt.upper()} файл в программе по умолчанию")
            else:
                status_parts.append(f".{fmt} не создан (см. предупреждения)")
                
        self.view.window().status_message("Генерация завершена: " + ", ".join(status_parts) + ".")

    def _show_progress(self, thread):
        """Показывает анимированный прогресс пока поток работает"""
        def update_status():
            dots = 0
            while thread.is_alive():
                dots = (dots + 1) % 4
                msg = f"Генерация изображений{'.' * dots}{' ' * (3 - dots)}"
                sublime.set_timeout(lambda m=msg: self.view.window().status_message(m), 0)
                time.sleep(0.5)
        
        progress_thread = threading.Thread(target=update_status)
        progress_thread.daemon = True
        progress_thread.start()

    def jar_exists(self):
        global PUML_JAR_PATH
        if os.path.exists(PUML_JAR_PATH):
            return True
        
        script_dir = os.path.dirname(__file__)
        for f in os.listdir(script_dir):
            if f.lower().startswith('plantuml') and f.lower().endswith('.jar'):
                PUML_JAR_PATH = os.path.join(script_dir, f)
                return True
        return False

    def _open_file_in_default_program(self, file_path):
        """Открывает файл в программе по умолчанию"""
        try:
            if sys.platform.startswith('win'):
                os.startfile(file_path)
            elif sys.platform.startswith('darwin'):
                subprocess.call(['open', file_path])
            else:
                subprocess.call(['xdg-open', file_path])
            return True
        except Exception as e:
            self._add_warning(f"Не удалось открыть файл {file_path}: {e}")
            return False

    def _add_warning(self, message):
        """Добавляет предупреждение в список"""
        full_msg = f"URQ to PlantUML Warning: {message}"
        self.warnings.append(full_msg)
        print(full_msg)

    def _print_warnings(self):
        """Выводит все накопленные предупреждения"""
        if self.warnings:
            print("\n" + "=" * 20 + " URQ to PlantUML Warnings " + "=" * 20)
            for warning in self.warnings:
                print(warning)
            print("=" * 61 + "\n")

class InsertTextCommand(sublime_plugin.TextCommand):
    def run(self, edit, text=""):
        self.view.insert(edit, 0, text)