import os
import sys
import subprocess
import tkinter as tk
from tkinter import filedialog

class FileDialogHelper:
    @staticmethod
    def _zenity_select(title, multiple=False, save=False):
        try:
            cmd = ["zenity", "--file-selection", f"--title={title}"]
            if multiple:
                cmd.extend(["--multiple", "--separator=|"])
            if save:
                cmd.extend(["--save", "--confirm-overwrite"])
            
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0:
                out = res.stdout.strip()
                return [p for p in out.split("|") if p] if multiple else out
        except Exception:
            pass
        return None

    @staticmethod
    def select_video_files():
        if sys.platform.startswith("linux"):
            res = FileDialogHelper._zenity_select("Selecione um ou mais vídeos", multiple=True)
            if res is not None:
                return res

        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        paths = filedialog.askopenfilenames(
            title="Selecione um ou mais vídeos",
            filetypes=[("Vídeos", "*.mp4 *.avi *.mov *.mkv"), ("Todos os arquivos", "*.*")]
        )
        root.destroy()
        return list(paths)

    @staticmethod
    def select_save_project_file():
        if sys.platform.startswith("linux"):
            res = FileDialogHelper._zenity_select("Salvar Projeto", save=True)
            if res:
                if not res.endswith(".json"):
                    res += ".json"
                return res

        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.asksaveasfilename(
            title="Salvar Projeto",
            defaultextension=".json",
            filetypes=[("Projeto VideoLabeler (*.json)", "*.json"), ("Todos os arquivos", "*.*")]
        )
        root.destroy()
        return path

    @staticmethod
    def select_open_project_file():
        if sys.platform.startswith("linux"):
            res = FileDialogHelper._zenity_select("Carregar Projeto")
            if res:
                return res

        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.askopenfilename(
            title="Carregar Projeto",
            filetypes=[("Projeto VideoLabeler (*.json)", "*.json"), ("Todos os arquivos", "*.*")]
        )
        root.destroy()
        return path