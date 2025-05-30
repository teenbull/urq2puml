# PlantUML Generator - сохраняет PUML файлы и генерирует диаграммы
import sublime
import os
import subprocess
import string
import base64
import zlib
import urllib.request
import urllib.error

try:
    from .puml_formatter import PumlFormatter
except ImportError:
    from puml_formatter import PumlFormatter

class PlantumlOnlineGen:
    """Онлайн генератор PlantUML"""
    def __init__(self, server_url="http://www.plantuml.com/plantuml/"):
        self.server_url = server_url
        self.p_alpha = string.digits + string.ascii_uppercase + string.ascii_lowercase + '-_'
        self.b64_alpha = string.ascii_uppercase + string.ascii_lowercase + string.digits + '+/'
        self.b64_to_p = str.maketrans(self.b64_alpha, self.p_alpha)

    def _req(self, type, text):
        """Запрос к серверу PlantUML"""
        enc = zlib.compress(text.encode('utf-8'))[2:-4]
        enc_b64 = base64.b64encode(enc).decode().translate(self.b64_to_p)
        url = f"{self.server_url}{type}/{enc_b64}"
        h = {'User-Agent': 'Sublime URQ2PUML'}
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30) as resp:
                if resp.getcode() == 200:
                    return resp.read()
                err_body = resp.read().decode(errors='replace') or "(empty)"
                err_msg = f"HTTP Error {resp.getcode()}: {resp.reason}. Body: {err_body}"
                print(f"Online Gen Error Details: {err_msg}")
                raise urllib.error.HTTPError(url, resp.getcode(), err_msg, resp.headers, None)
        except urllib.error.HTTPError:
            raise
        except Exception as e:
            raise RuntimeError(f"Сервер PlantUML ({type(e).__name__}) ошибка: {e}")

    def generate_png(self, puml_text):
        """Генерирует PNG"""
        return self._req("img", puml_text)

    def generate_svg(self, puml_text):
        """Генерирует SVG"""
        return self._req("svg", puml_text)

class PlantumlGen:
    """Генератор PlantUML файлов и диаграмм"""
    def __init__(self, jar_path=None):
        self.jar_path = jar_path
        self.warnings = []
        self.formatter = PumlFormatter()

    def save_puml(self, locs, output_file):
        """Сохраняет PUML файл"""
        content = self.formatter.format_puml(locs)
        self.warnings.extend(self.formatter.get_warnings())
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"PlantUML Gen: Файл создан: {output_file}")
        except Exception as e:
            raise Exception(f"Ошибка записи файла {output_file}: {e}")
        
        return content

    def generate_local(self, puml_file, file_type):
        """Генерирует файл через локальный PlantUML"""
        if not self.jar_path or not os.path.exists(self.jar_path):
            self._add_warning(f"PlantUML JAR не найден: {self.jar_path}")
            return False
        
        if not os.path.exists(puml_file):
            self._add_warning(f"PUML файл не найден: {puml_file}")
            return False
        
        type_flags = {'png': '-tpng', 'svg': '-tsvg'}
        if file_type not in type_flags:
            self._add_warning(f"Неподдерживаемый тип файла: {file_type}")
            return False
        
        print(f"PlantUML Gen: {file_type.upper()} файл генерируется...")
        
        cmd = [
            'java', 
            '-Dfile.encoding=UTF-8',
            '-jar', self.jar_path,
            type_flags[file_type],
            '-charset', 'UTF-8',
            puml_file
        ]
        
        try:
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=os.path.dirname(puml_file),
                universal_newlines=True,
                startupinfo=startupinfo
            )
            stdout, stderr = process.communicate()
            returncode = process.returncode
        except FileNotFoundError:
            self._add_warning("Java не найдена в PATH")
            sublime.error_message("Java не найдена в PATH, попробуйте установить и прописать.")
            return False
        except Exception as e:
            self._add_warning(f"Ошибка PlantUML для {file_type.upper()}: {e}")
            return False
        
        if returncode == 0:
            output_file = os.path.splitext(puml_file)[0] + '.' + file_type
            if os.path.exists(output_file):
                print(f"PlantUML Gen: {file_type.upper()} создан: {output_file}")
                return True
            else:
                self._add_warning(f"{file_type.upper()} файл не создан")
                return False
        else:
            error_msg = stderr.strip() if stderr else "Неизвестная ошибка"
            self._add_warning(f"PlantUML ошибка {file_type.upper()}: {error_msg}")
            return False

    def generate_online(self, puml_content, puml_file, file_type):
        """Генерирует файл через онлайн сервис"""
        try:
            print(f"PlantUML Gen: {file_type.upper()} генерируется онлайн...")
            
            gen = PlantumlOnlineGen()
            data = gen.generate_png(puml_content) if file_type == 'png' else gen.generate_svg(puml_content)
            
            output_file = os.path.splitext(puml_file)[0] + '.' + file_type
            with open(output_file, 'wb') as f:
                f.write(data)
           
            print(f"PlantUML Gen: {file_type.upper()} создан онлайн: {output_file}")
            return True
            
        except Exception as e:
            self._add_warning(f"Онлайн ошибка {file_type.upper()}: {e}")
            sublime.error_message("Ошибка при попытке онлайн генерации. Возможно, файл слишком велик - попробуйте оффлайн способ (см. readme.md).")
            return False

    def _add_warning(self, message):
        """Добавляет предупреждение"""
        self.warnings.append(f"PlantUML Gen Warning: {message}")

    def get_warnings(self):
        """Возвращает предупреждения"""
        combined_warnings = self.warnings + self.formatter.get_warnings()
        return combined_warnings