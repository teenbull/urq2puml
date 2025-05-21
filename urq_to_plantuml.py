import sublime
import sublime_plugin
import os
import re
import tempfile
import platform
import subprocess
import urllib.request
import urllib.parse
import base64
import zlib
import io
import string

class UrqToPlantumlCommand(sublime_plugin.TextCommand):
    def run(self, edit, nopng=False):
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
            
            # Если nopng не задан, то генерируем PNG
            if not nopng:
                # Создаем путь к выходному .png файлу
                png_file = os.path.splitext(current_file)[0] + '.png'
                
                # Генерируем изображение через python-plantuml
                success = self._generate_diagram(plantuml_code, png_file)
                
                if success:
                    # Открываем сгенерированный файл PlantUML в Sublime
                    self.view.window().open_file(puml_file)
                    self._open_image(png_file)
                    
                    # Показываем сообщение об успешной конвертации
                    self.view.window().status_message("Конвертация URQ в PlantUML завершена успешно")
                else:
                    sublime.error_message("Ошибка при создании диаграммы. Проверьте подключение к интернету.")
            else:
                # Открываем только PUML файл без генерации PNG
                self.view.window().open_file(puml_file)
                self.view.window().status_message("Конвертация URQ в PlantUML завершена успешно (без PNG)")
                
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
        # Загружаем стили из файла шаблонов
        style_name = self.view.settings().get("urq_to_plantuml_style", "fantasy")
        style = self._get_style(style_name)
        
        plantuml_code = "@startuml\n"
        
        # Добавляем настройки стиля
        plantuml_code += style
        
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

    def _get_style(self, style_name="default"):
        """Получает стиль из файла шаблонов"""
        try:
            # Путь к файлу шаблонов рядом с модулем плагина
            plugin_folder = os.path.dirname(os.path.abspath(__file__))
            templates_file = os.path.join(plugin_folder, "templates.json")
            
            # Если файл шаблонов не существует, используем стиль по умолчанию
            if not os.path.exists(templates_file):
                return self._get_default_style()
            
            # Загружаем шаблоны из файла
            with open(templates_file, 'r', encoding='utf-8') as f:
                templates = sublime.decode_value(f.read())
            
            # Получаем запрошенный стиль или стиль по умолчанию
            if style_name in templates:
                return templates[style_name]
            else:
                # Исправлено - убраны f-строки
                sublime.status_message("Стиль '{0}' не найден, используется стиль по умолчанию".format(style_name))
                return templates.get("default", self._get_default_style())
                
        except Exception as e:
            # Исправлено - убраны f-строки
            sublime.error_message("Ошибка при загрузке стилей: {0}".format(str(e)))
            return self._get_default_style()

    def _get_default_style(self):
        """Возвращает стиль по умолчанию, если файл шаблонов недоступен"""
        return """skinparam state {
      BackgroundColor LightBlue
      BorderColor Blue
      FontName Arial
    }

    """
    
    def _generate_diagram(self, plantuml_code, output_image):
        """Генерирует изображение через встроенный механизм PlantUML"""
        try:
            # Используем встроенную реализацию PlantUML
            plantuml_generator = EmbeddedPlantumlGenerator()
            
            # Генерируем диаграмму и сохраняем в файл
            with open(output_image, 'wb') as f:
                diagram = plantuml_generator.generate_png(plantuml_code)
                f.write(diagram)
            
            return True
        except Exception as e:
            sublime.error_message("Ошибка при создании диаграммы: " + str(e))
            return False
    
    def _open_image(self, image_path):        
        """Открывает изображение в Sublime Text"""
        try:
            # Открываем изображение в Sublime Text вместо системного просмотрщика
            self.view.window().open_file(image_path)
            return True
        except Exception as e:
            sublime.error_message("Не удалось открыть изображение: " + str(e))
            return False        
        # """Открывает изображение в системном просмотрщике"""
        # try:
        #     # Определяем команду для открытия изображения в зависимости от ОС
        #     system = platform.system()
            
        #     if system == "Windows":
        #         os.startfile(image_path)
        #     elif system == "Darwin":  # macOS
        #         subprocess.Popen(["open", image_path])
        #     else:  # Linux и другие Unix-подобные системы
        #         subprocess.Popen(["xdg-open", image_path])
                
        #     return True
        # except Exception as e:
        #     sublime.error_message("Не удалось открыть изображение: " + str(e))
        #     return False


class UrqToPlantumlNoPngCommand(sublime_plugin.TextCommand):
    """Команда для запуска плагина без генерации PNG файла"""
    def run(self, edit):
        self.view.run_command('urq_to_plantuml', {'nopng': True})


# Встроенная реализация PlantUML (на основе python-plantuml)
class EmbeddedPlantumlGenerator:
    """Встроенная реализация для генерации PlantUML диаграмм без зависимостей"""
    def __init__(self, server_url="http://www.plantuml.com/plantuml/img/"):
        self.server_url = server_url
        # Создаем таблицу для трансляции символов base64 в символы plantuml
        self.plantuml_alphabet = string.digits + string.ascii_uppercase + string.ascii_lowercase + '-_'
        self.base64_alphabet = string.ascii_uppercase + string.ascii_lowercase + string.digits + '+/'
        self.b64_to_plantuml = str.maketrans(self.base64_alphabet, self.plantuml_alphabet)
    
    def generate_png(self, plantuml_text):
        """Генерирует PNG-изображение из PlantUML кода"""
        encoded = self.deflate_and_encode(plantuml_text)
        url = self.server_url + encoded
        
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Sublime Text Plugin'}
        req = urllib.request.Request(url, headers=headers)
        
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.read()
    
    def deflate_and_encode(self, plantuml_text):
        """Сжимает PlantUML текст и кодирует его для сервера PlantUML."""
        zlibbed_str = zlib.compress(plantuml_text.encode('utf-8'))
        compressed_string = zlibbed_str[2:-4]  # Убираем заголовок zlib (2 байта) и контрольную сумму (4 байта)
        b64_encoded = base64.b64encode(compressed_string).decode('utf-8')
        return b64_encoded.translate(self.b64_to_plantuml)