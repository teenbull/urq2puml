import sublime
import sublime_plugin
import os
import re
import subprocess
import platform
import tempfile
import base64
import zlib

class UrqToPlantumlCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        # Получаем путь к текущему файлу
        current_file = self.view.file_name()
        
        # Проверяем, что текущий файл - это qst файл
        if not current_file or not current_file.lower().endswith('.qst'):
            sublime.error_message("Текущий файл не является URQ (.qst) файлом")
            return
            
        # Определяем путь к директории, где находится плагин
        plugin_path = os.path.dirname(os.path.realpath(__file__))
        
        # Путь к plantuml.jar (должен быть в той же папке, что и плагин)
        plantuml_jar = os.path.join(plugin_path, "plantuml.jar")
        
        # Проверяем, что plantuml.jar существует
        if not os.path.exists(plantuml_jar):
            sublime.error_message("Не найден файл plantuml.jar в " + plugin_path)
            return
        
        # Определяем путь к Java
        java_cmd = self._get_java_cmd()
        
        if not java_cmd:
            sublime.error_message("Не удалось найти Java в системе")
            return
        
        # Показываем статус
        self.view.window().status_message("Конвертация URQ в PlantUML...")
        
        try:
            # Парсим URQ файл
            locations, transitions = self._parse_urq_file(current_file)
            
            # Создаем путь к выходному .puml файлу
            puml_file = os.path.splitext(current_file)[0] + '.puml'
            
            # Генерируем PlantUML код
            plantuml_code = self._generate_plantuml(locations, transitions, puml_file)
            
            # Генерируем изображение
            self._generate_diagram(puml_file, plantuml_jar, java_cmd)
            
            # Открываем сгенерированный файл PlantUML в Sublime
            self.view.window().open_file(puml_file)
            
            # Показываем сообщение об успешной конвертации
            self.view.window().status_message("Конвертация URQ в PlantUML завершена успешно")
            
        except Exception as e:
            sublime.error_message("Произошла ошибка при конвертации: " + str(e))
    
    def _get_java_cmd(self):
        """Определяет команду для запуска Java, используя PATH"""
        system = platform.system()
        
        java_cmd = "java"
        
        # Проверяем команду из PATH
        try:
            startupinfo = None
            if system == "Windows":
                # На Windows скрываем окно консоли
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0  # SW_HIDE
            
            process = subprocess.Popen(
                [java_cmd, "-version"], 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                universal_newlines=True,
                startupinfo=startupinfo
            )
            stdout, stderr = process.communicate()
            
            # Java версия обычно выводится в stderr
            if "version" in stderr or "version" in stdout:
                return java_cmd
        except:
            pass
        
        # Проверка стандартных расположений для разных OS
        if system == "Windows":
            # Проверяем Java в Program Files
            program_dirs = [
                os.environ.get('PROGRAMFILES', 'C:\\Program Files'),
                os.environ.get('PROGRAMFILES(X86)', 'C:\\Program Files (x86)')
            ]
            
            for prog_dir in program_dirs:
                if os.path.exists(prog_dir):
                    java_path = os.path.join(prog_dir, 'Java')
                    if os.path.exists(java_path):
                        for item in os.listdir(java_path):
                            if item.startswith('jdk') or item.startswith('jre'):
                                bin_path = os.path.join(java_path, item, 'bin', 'java.exe')
                                if os.path.exists(bin_path):
                                    return bin_path
        
        elif system in ["Darwin", "Linux"]:
            # Для macOS и Linux проверяем стандартные пути
            java_paths = [
                "/usr/bin/java",
                "/usr/local/bin/java",
                "/opt/homebrew/bin/java"  # для macOS с Homebrew
            ]
            
            for path in java_paths:
                if os.path.exists(path):
                    return path
        
        # Если Java не найден, возвращаем None
        return None
    
    def _parse_urq_file(self, file_path):
        """Парсит URQ файл и возвращает структуру локаций и переходов"""
        try:
            # Сначала пробуем открыть с UTF-8
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            # Если не получилось, пробуем с cp1251
            with open(file_path, 'r', encoding='cp1251') as f:
                content = f.read()
        
        # Разбиваем файл на локации
        locations = {}
        transitions = []
        
        # Находим все локации (метки)
        location_blocks = re.split(r':([^\n]+)', content)[1:]  # Пропускаем первый элемент (текст до первой метки)
        
        for i in range(0, len(location_blocks), 2):
            if i+1 < len(location_blocks):
                location_name = location_blocks[i].strip()
                location_content = location_blocks[i+1].strip()
                
                # Извлекаем первое предложение из первого pln
                pln_match = re.search(r'pln\s+([^.\n]+)', location_content)
                description = pln_match.group(1).strip() if pln_match else "Нет описания"
                
                # Обрезаем длинные описания
                if len(description) > 40:
                    description = description[:37] + "..."
                
                locations[location_name] = description
                
                # Находим все btn в этой локации
                btn_matches = re.finditer(r'btn\s+([^,\n]+),\s*([^\n]+)', location_content)
                for match in btn_matches:
                    target_location = match.group(1).strip()
                    button_text = match.group(2).strip()
                    transitions.append((location_name, target_location, button_text))
        
        return locations, transitions
    
    def _generate_plantuml(self, locations, transitions, output_file):
        """Генерирует PlantUML код на основе локаций и переходов"""
        plantuml_code = "@startuml\n"
        
        # Добавляем настройки для красивого отображения
        plantuml_code += "skinparam state {\n"
        plantuml_code += "  BackgroundColor LightBlue\n"
        plantuml_code += "  BorderColor Blue\n"
        plantuml_code += "  FontName Arial\n"
        plantuml_code += "}\n\n"
        
        # Определяем состояния (локации)
        for name, description in locations.items():
            # Экранируем кавычки в описании
            description = description.replace('"', '\\"')
            plantuml_code += 'state "{0}\\n{1}" as {2}\n'.format(name, description, name.replace(" ", "_"))
        
        plantuml_code += "\n"
        
        # Определяем переходы
        for source, target, label in transitions:
            # Экранируем кавычки в тексте кнопки
            label = label.replace('"', '\\"')
            if label and len(label) > 20:
                label = label[:17] + "..."
            
            # Проверяем, существует ли целевая локация
            if target in locations:
                plantuml_code += '{0} --> {1} : "{2}"\n'.format(
                    source.replace(" ", "_"), 
                    target.replace(" ", "_"), 
                    label
                )
        
        plantuml_code += "@enduml"
        
        # Записываем PlantUML код в файл
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(plantuml_code)
        
        return plantuml_code
    
    def _generate_diagram(self, plantuml_file, plantuml_jar, java_cmd, method="jar"):
        """Генерирует изображение на основе PlantUML кода"""
        try:
            # Определяем выходной файл изображения
            output_image = os.path.splitext(plantuml_file)[0] + ".png"
            
            if method == "jar":
                # Используем локальный JAR-файл
                startupinfo = None
                if platform.system() == "Windows":
                    # На Windows скрываем окно консоли
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = 0  # SW_HIDE
                
                cmd = [java_cmd, "-jar", plantuml_jar, plantuml_file]
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                    startupinfo=startupinfo
                )
                stdout, stderr = process.communicate()
                
                if process.returncode != 0:
                    raise Exception("Ошибка при выполнении PlantUML: " + stderr)
            
            elif method == "server":
                # Загружаем PlantUML код из файла
                with open(plantuml_file, 'r', encoding='utf-8') as f:
                    plantuml_code = f.read()
                
                # Используем онлайн-сервер
                encoded = self._encode_for_plantuml_server(plantuml_code)
                url = "http://www.plantuml.com/plantuml/png/{0}".format(encoded)
                
                # Используем urllib для HTTP запроса
                try:
                    import urllib.request
                    response = urllib.request.urlopen(url)
                    if response.getcode() == 200:
                        with open(output_image, 'wb') as f:
                            f.write(response.read())
                    else:
                        raise Exception("Ошибка сервера: {0}".format(response.getcode()))
                except ImportError:
                    # Для Python 2.x
                    import urllib2
                    response = urllib2.urlopen(url)
                    if response.getcode() == 200:
                        with open(output_image, 'wb') as f:
                            f.write(response.read())
                    else:
                        raise Exception("Ошибка сервера: {0}".format(response.getcode()))
            
            return True
        
        except Exception as e:
            sublime.error_message("Ошибка при генерации диаграммы: " + str(e))
            return False
    
    def _encode_for_plantuml_server(self, plantuml_text):
        """Кодирует PlantUML текст для использования с онлайн-сервером"""
        compressed = zlib.compress(plantuml_text.encode('utf-8'))
        b64 = base64.b64encode(compressed)
        return b64.decode('utf-8')