import sys
import subprocess
import json
import pygame

class ConfirmationModal:
    """Caixa de diálogo Pop-up interna com suporte a cliques e teclado (Enter / ESC)."""
    def __init__(self, screen, title, message):
        self.screen = screen
        self.title = title
        self.message = message
        self.font_title = pygame.font.Font(None, 26)
        self.font_msg = pygame.font.Font(None, 20)
        self.rect = pygame.Rect(0, 0, 480, 200)
        self.rect.center = (screen.get_width() // 2, screen.get_height() // 2)

        self.btn_confirm = pygame.Rect(self.rect.x + 80, self.rect.y + 140, 130, 35)
        self.btn_cancel = pygame.Rect(self.rect.x + 270, self.rect.y + 140, 130, 35)

    def draw(self):
        overlay = pygame.Surface((self.screen.get_width(), self.screen.get_height()), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))

        pygame.draw.rect(self.screen, (40, 40, 40), self.rect, border_radius=8)
        pygame.draw.rect(self.screen, (200, 100, 50), self.rect, 2, border_radius=8)

        t_surf = self.font_title.render(self.title, True, (255, 200, 100))
        self.screen.blit(t_surf, (self.rect.x + 20, self.rect.y + 20))

        words = self.message.split(' ')
        lines, curr = [], ""
        for w in words:
            if len(curr + " " + w) > 45:
                lines.append(curr)
                curr = w
            else:
                curr += " " + w
        lines.append(curr)

        y_off = self.rect.y + 60
        for line in lines:
            m_surf = self.font_msg.render(line.strip(), True, (220, 220, 220))
            self.screen.blit(m_surf, (self.rect.x + 20, y_off))
            y_off += 22

        m_pos = pygame.mouse.get_pos()
        c_color = (180, 50, 50) if self.btn_confirm.collidepoint(m_pos) else (140, 40, 40)
        a_color = (100, 100, 100) if self.btn_cancel.collidepoint(m_pos) else (70, 70, 70)

        pygame.draw.rect(self.screen, c_color, self.btn_confirm, border_radius=5)
        pygame.draw.rect(self.screen, a_color, self.btn_cancel, border_radius=5)

        t_conf = self.font_msg.render("Enter [Confirmar]", True, (255, 255, 255))
        t_canc = self.font_msg.render("ESC [Cancelar]", True, (255, 255, 255))

        self.screen.blit(t_conf, t_conf.get_rect(center=self.btn_confirm.center))
        self.screen.blit(t_canc, t_canc.get_rect(center=self.btn_cancel.center))

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.btn_confirm.collidepoint(event.pos):
                return True
            if self.btn_cancel.collidepoint(event.pos):
                return False

        elif event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                return True
            elif event.key == pygame.K_ESCAPE:
                return False

        return None


class FileDialogHelper:
    @staticmethod
    def select_video_files():
        """Abre a caixa de diálogo nativa do sistema operacional."""
        file_paths = []

        if sys.platform == "win32":
            ps_script = """
            Add-Type -AssemblyName System.Windows.Forms
            $f = New-Object System.Windows.Forms.OpenFileDialog
            $f.Multiselect = $true
            $f.Title = "Selecionar Vídeos para a Timeline"
            $f.Filter = "Vídeos (*.mp4;*.avi;*.mkv;*.mov)|*.mp4;*.avi;*.mkv;*.mov|Todos os Arquivos (*.*)|*.*"
            if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
                $f.FileNames | ConvertTo-Json -Compress
            }
            """
            try:
                creation_flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                res = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", ps_script],
                    capture_output=True, text=True, creationflags=creation_flags
                )
                out = res.stdout.strip()
                if out:
                    parsed = json.loads(out)
                    file_paths = parsed if isinstance(parsed, list) else [parsed]
            except Exception as e:
                print(f"Erro no seletor Windows: {e}")

        elif sys.platform == "darwin":
            applescript = '''
            set theFiles to choose file with prompt "Selecionar Vídeos" of type {"mp4", "avi", "mkv", "mov"} with multiple selections allowed
            set posixPaths to {}
            repeat with aFile in theFiles
                set end of posixPaths to POSIX path of aFile
            end repeat
            local ASTID
            set ASTID to AppleScript's text item delimiters
            set AppleScript's text item delimiters to ASCII character 10
            set theString to posixPaths as string
            set AppleScript's text item delimiters to ASTID
            return theString
            '''
            try:
                res = subprocess.run(["osascript", "-e", applescript], capture_output=True, text=True)
                out = res.stdout.strip()
                if out:
                    file_paths = out.split("\n")
            except Exception as e:
                print(f"Erro no seletor macOS: {e}")

        else:
            try:
                res = subprocess.run(
                    ["zenity", "--file-selection", "--multiple", "--separator=\n",
                     '--file-filter=Vídeos (*.mp4 *.avi *.mkv *.mov) | *.mp4 *.avi *.mkv *.mov'],
                    capture_output=True, text=True
                )
                out = res.stdout.strip()
                if out:
                    file_paths = out.split("\n")
            except FileNotFoundError:
                print("Zenity não encontrado no Linux.")

        return file_paths