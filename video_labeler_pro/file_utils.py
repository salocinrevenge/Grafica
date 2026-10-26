import os
import sys
import subprocess

class FileDialogHelper:
    @staticmethod
    def select_video_files():
        """Abre caixa de diálogo nativa para selecionar múltiplos vídeos."""
        if sys.platform == "win32":
            ps_script = """
            [System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms") | Out-Null
            $dialog = New-Object System.Windows.Forms.OpenFileDialog
            $dialog.Multiselect = $true
            $dialog.Filter = "Arquivos de Vídeo|*.mp4;*.avi;*.mov;*.mkv;*.webm|Todos os Arquivos|*.*"
            if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
                $dialog.FileNames -join "`n"
            }
            """
            res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], capture_output=True, text=True)
            files = [f.strip() for f in res.stdout.strip().split("\n") if f.strip()]
            return files

        elif sys.platform == "darwin":
            script = 'set theFiles to choose file with prompt "Selecionar Arquivos de Vídeo" of type {"mp4", "avi", "mov", "mkv", "webm"} with multiple selections allowed\n' \
                     'repeat with aFile in theFiles\n' \
                     '    log POSIX path of aFile\n' \
                     'end repeat'
            res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
            files = [f.strip() for f in res.stderr.strip().split("\n") if f.strip()]
            return files

        else: # Linux
            try:
                res = subprocess.run(["zenity", "--file-selection", "--multiple", "--file-filter=Vídeos | *.mp4 *.avi *.mov *.mkv *.webm"], capture_output=True, text=True)
                if res.returncode == 0:
                    return [f.strip() for f in res.stdout.strip().split("|") if f.strip()]
            except Exception:
                pass
            return []

    @staticmethod
    def select_label_files():
        """Abre caixa de diálogo nativa para selecionar até dois arquivos JSON de labels hierárquicas."""
        if sys.platform == "win32":
            ps_script = """
            [System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms") | Out-Null
            $dialog = New-Object System.Windows.Forms.OpenFileDialog
            $dialog.Multiselect = $true
            $dialog.Filter = "Arquivos de Labels (*.json)|*.json|Todos os Arquivos|*.*"
            if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
                $dialog.FileNames -join "`n"
            }
            """
            res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], capture_output=True, text=True)
            files = [f.strip() for f in res.stdout.strip().split("\n") if f.strip()]
            return files[:2]

        elif sys.platform == "darwin":
            script = 'set theFiles to choose file with prompt "Selecionar Labels Hierárquicas (até 2)" of type {"json"} with multiple selections allowed\n' \
                     'repeat with aFile in theFiles\n' \
                     '    log POSIX path of aFile\n' \
                     'end repeat'
            res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
            files = [f.strip() for f in res.stderr.strip().split("\n") if f.strip()]
            return files[:2]

        else: # Linux
            try:
                res = subprocess.run(["zenity", "--file-selection", "--multiple", "--file-filter=Labels (*.json) | *.json"], capture_output=True, text=True)
                if res.returncode == 0:
                    files = [f.strip() for f in res.stdout.strip().split("|") if f.strip()]
                    return files[:2]
            except Exception:
                pass
            return []

    @staticmethod
    def select_save_project_file():
        """Abre caixa de diálogo nativa para salvar arquivo JSON."""
        if sys.platform == "win32":
            ps_script = """
            [System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms") | Out-Null
            $dialog = New-Object System.Windows.Forms.SaveFileDialog
            $dialog.Filter = "Projeto VideoLabeler (*.json)|*.json"
            $dialog.DefaultExt = "json"
            if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
                $dialog.FileName
            }
            """
            res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], capture_output=True, text=True)
            return res.stdout.strip()

        elif sys.platform == "darwin":
            script = 'set theFile to choose file name with prompt "Salvar Projeto" default name "projeto.json"\nPOSIX path of theFile'
            res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
            return res.stdout.strip()

        else: # Linux
            try:
                res = subprocess.run(["zenity", "--file-selection", "--save", "--confirm-overwrite", "--filename=projeto.json"], capture_output=True, text=True)
                if res.returncode == 0:
                    return res.stdout.strip()
            except Exception:
                pass
            return ""

    @staticmethod
    def select_open_project_file():
        """Abre caixa de diálogo nativa para carregar projeto JSON."""
        if sys.platform == "win32":
            ps_script = """
            [System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms") | Out-Null
            $dialog = New-Object System.Windows.Forms.OpenFileDialog
            $dialog.Filter = "Projeto VideoLabeler (*.json)|*.json"
            if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
                $dialog.FileName
            }
            """
            res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], capture_output=True, text=True)
            return res.stdout.strip()

        elif sys.platform == "darwin":
            script = 'set theFile to choose file with prompt "Carregar Projeto" of type {"json"}\nPOSIX path of theFile'
            res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
            return res.stdout.strip()

        else: # Linux
            try:
                res = subprocess.run(["zenity", "--file-selection", "--file-filter=Projeto (*.json) | *.json"], capture_output=True, text=True)
                if res.returncode == 0:
                    return res.stdout.strip()
            except Exception:
                pass
            return ""

    @staticmethod
    def select_export_directory():
        """Abre caixa de diálogo nativa para selecionar pasta de exportação."""
        if sys.platform == "win32":
            ps_script = """
            [System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms") | Out-Null
            $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
            $dialog.Description = "Selecionar Pasta para Exportar"
            if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
                $dialog.SelectedPath
            }
            """
            res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], capture_output=True, text=True)
            return res.stdout.strip()

        elif sys.platform == "darwin":
            script = 'set theFolder to choose folder with prompt "Selecionar Pasta para Exportar"\nPOSIX path of theFolder'
            res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
            return res.stdout.strip()

        else: # Linux
            try:
                res = subprocess.run(["zenity", "--file-selection", "--directory"], capture_output=True, text=True)
                if res.returncode == 0:
                    return res.stdout.strip()
            except Exception:
                pass
            return ""