import sublime
import sublime_plugin
import os
import re
import urllib.request
import urllib.error
import base64
import zlib
import tempfile
import platform
import subprocess
import time

class UrqToPlantumlCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        # Получаем путь к текущему файлу
        current_file = self.view.file_name()
        
        # Проверяем, что текущий файл - это qst файл
        if not current_file or not current_file.lower().endswith('.qst'):
            sublime.error_message("Текущий файл не является URQ (.qst) файлом")
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
            
            # Создаем путь к выходному .png файлу
            png_file = os.path.splitext(current_file)[0] + '.png'
            
            # Генерируем изображение через онлайн-сервер
            success = self._generate_diagram_server(plantuml_code, png_file)
            
            if success:
                # Открываем сгенерированный файл PlantUML в Sublime
                self.view.window().open_file(puml_file)
                
                # Показываем сообщение об успешной конвертации
                self.view.window().status_message("Конвертация URQ в PlantUML завершена успешно")
            else:
                sublime.error_message("Ошибка при создании диаграммы. Проверьте подключение к интернету.")
                
        except Exception as e:
            sublime.error_message("Произошла ошибка при конвертации: " + str(e))
    
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
    
    def _encode_for_plantuml_server(self, plantuml_text):
        """Кодирует PlantUML текст для использования с онлайн-сервером"""
        compressed = zlib.compress(plantuml_text.encode('utf-8'))
        b64 = base64.b64encode(compressed)
        return b64.decode('utf-8')
    
    def _generate_diagram_server(self, plantuml_code, output_image):
        """Генерирует изображение через онлайн-сервер PlantUML"""
        try:
            # Используем онлайн-сервер
            encoded = self._encode_for_plantuml_server(plantuml_code)
            url = "http://www.plantuml.com/plantuml/png/{0}".format(encoded)
            
            # Добавляем заголовок User-Agent для предотвращения блокировки
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Sublime Text Plugin'}
            
            # Создаем запрос с заголовками
            req = urllib.request.Request(url, headers=headers)
            
            # Загружаем изображение
            with urllib.request.urlopen(req, timeout=30) as response:
                if response.getcode() == 200:
                    # Сохраняем изображение
                    with open(output_image, 'wb') as f:
                        f.write(response.read())
                    return True
                else:
                    return False
        except Exception as e:
            sublime.error_message("Ошибка при загрузке с сервера PlantUML: " + str(e))
            return False
    
    def _open_image(self, image_path):
        """Открывает изображение в системном просмотрщике"""
        try:
            # Определяем команду для открытия изображения в зависимости от ОС
            system = platform.system()
            
            if system == "Windows":
                os.startfile(image_path)
            elif system == "Darwin":  # macOS
                subprocess.Popen(["open", image_path])
            else:  # Linux и другие Unix-подобные системы
                subprocess.Popen(["xdg-open", image_path])
                
            return True
        except Exception as e:
            sublime.error_message("Не удалось открыть изображение: " + str(e))
            return False

# Альтернативный метод для использования с библиотекой requests,
# если она доступна (для более стабильной работы с HTTP)
class UrqToPlantumlRequestsCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        # Проверяем наличие библиотеки requests
        try:
            import requests
            self._use_requests = True
        except ImportError:
            self._use_requests = False
            sublime.error_message("Библиотека requests не установлена. Будет использован стандартный метод.")
            
        # Вызываем стандартный метод
        self.view.run_command('urq_to_plantuml')

    def _generate_diagram_server_with_requests(self, plantuml_code, output_image):
        """Генерирует изображение через онлайн-сервер PlantUML с использованием библиотеки requests"""
        try:
            import requests
            
            # Используем онлайн-сервер
            encoded = self._encode_for_plantuml_server(plantuml_code)
            url = "http://www.plantuml.com/plantuml/png/~{0}".format(encoded)
            
            # Добавляем заголовок User-Agent для предотвращения блокировки
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Sublime Text Plugin'}
            
            # Выполняем запрос
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                # Сохраняем изображение
                with open(output_image, 'wb') as f:
                    f.write(response.content)
                return True
            else:
                return False
        except Exception as e:
            sublime.error_message("Ошибка при загрузке с сервера PlantUML: " + str(e))
            return False