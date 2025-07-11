import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox
import subprocess
import os
import sys
import threading
import time

class FlaskRunnerApp:
    def __init__(self, master):
        self.master = master
        master.title("Golbal Business App")
        master.geometry("800x600") # Set initial window size
        master.resizable(True, True) # Allow resizing

        self.flask_process = None
        self.selected_folder = tk.StringVar()
        self.status_message = tk.StringVar()
        self.status_message.set("Ready to run your Flask app.")

        # --- Styling ---
        bg_color = "#f0f2f5" # Light gray background
        button_color = "#4CAF50" # Green for run
        stop_button_color = "#f44336" # Red for stop
        text_color = "#333333"
        font_style = ("Inter", 10)
        heading_font_style = ("Inter", 12, "bold")

        master.configure(bg=bg_color)

        # --- Main Frame ---
        main_frame = tk.Frame(master, bg=bg_color, padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- Folder Selection Section ---
        folder_frame = tk.Frame(main_frame, bg=bg_color, bd=2, relief="groove", padx=10, pady=10)
        folder_frame.pack(fill=tk.X, pady=10)

        tk.Label(folder_frame, text="Select Flask App Folder:", font=heading_font_style, bg=bg_color, fg=text_color).pack(anchor=tk.W, pady=(0, 5))

        self.folder_entry = tk.Entry(folder_frame, textvariable=self.selected_folder, width=60, font=font_style, state="readonly", relief="flat", bg="#e0e0e0", fg=text_color)
        self.folder_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        browse_button = tk.Button(folder_frame, text="Browse", command=self.browse_folder, font=font_style, bg="#007bff", fg="white", activebackground="#0056b3", relief="raised", bd=2)
        browse_button.pack(side=tk.RIGHT)

        # --- App Control Buttons ---
        button_frame = tk.Frame(main_frame, bg=bg_color, pady=10)
        button_frame.pack(fill=tk.X)

        self.run_button = tk.Button(button_frame, text="Run Flask App", command=self.run_flask_app, font=heading_font_style, bg=button_color, fg="white", activebackground="#45a049", relief="raised", bd=3, padx=15, pady=8)
        self.run_button.pack(side=tk.LEFT, padx=(0, 10), expand=True)

        self.stop_button = tk.Button(button_frame, text="Stop Flask App", command=self.stop_flask_app, font=heading_font_style, bg=stop_button_color, fg="white", activebackground="#d32f2f", relief="raised", bd=3, padx=15, pady=8, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, expand=True)

        # --- Status and Output Area ---
        status_frame = tk.Frame(main_frame, bg=bg_color, bd=2, relief="groove", padx=10, pady=10)
        status_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        tk.Label(status_frame, textvariable=self.status_message, font=heading_font_style, bg=bg_color, fg=text_color).pack(anchor=tk.W, pady=(0, 5))

        self.output_text = scrolledtext.ScrolledText(status_frame, wrap=tk.WORD, height=15, font=font_style, bg="#ffffff", fg=text_color, relief="sunken", bd=1)
        self.output_text.pack(fill=tk.BOTH, expand=True)
        self.output_text.tag_configure("info", foreground="blue")
        self.output_text.tag_configure("error", foreground="red")
        self.output_text.tag_configure("success", foreground="green")

        # Handle window closing
        master.protocol("WM_DELETE_WINDOW", self.on_closing)

    def log_output(self, message, tag=None):
        """Appends a message to the output text area."""
        self.output_text.insert(tk.END, message + "\n", tag)
        self.output_text.see(tk.END) # Scroll to the end

    def browse_folder(self):
        """Opens a dialog to select a folder."""
        folder_path = filedialog.askdirectory()
        if folder_path:
            self.selected_folder.set(folder_path)
            self.log_output(f"Selected folder: {folder_path}", "info")
            self.status_message.set(f"Folder selected: {os.path.basename(folder_path)}")
            self.run_button.config(state=tk.NORMAL) # Enable run button once folder is selected

    def run_flask_app(self):
        """Attempts to run the Flask application in the selected folder."""
        app_folder = self.selected_folder.get()
        if not app_folder:
            messagebox.showerror("Error", "Please select a Flask application folder first.")
            return

        if not os.path.isdir(app_folder):
            messagebox.showerror("Error", "Selected path is not a valid directory.")
            return

        if self.flask_process and self.flask_process.poll() is None:
            messagebox.showinfo("Info", "Flask app is already running.")
            return

        self.log_output(f"Attempting to run Flask app from: {app_folder}", "info")
        self.status_message.set("Starting Flask app...")
        self.run_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.DISABLED) # Disable stop until process starts

        # Use a thread to run the Flask app to keep the GUI responsive
        self.flask_thread = threading.Thread(target=self._run_flask_in_thread, args=(app_folder,))
        self.flask_thread.daemon = True # Allow the thread to exit when the main program exits
        self.flask_thread.start()

    def _run_flask_in_thread(self, app_folder):
        """Internal method to run Flask app in a separate thread."""
        try:
            # Check for requirements.txt and install dependencies
            requirements_path = os.path.join(app_folder, "requirements.txt")
            if os.path.exists(requirements_path):
                self.log_output("Installing dependencies from requirements.txt...", "info")
                pip_install_cmd = [sys.executable, "-m", "pip", "install", "-r", requirements_path]
                try:
                    pip_result = subprocess.run(pip_install_cmd, cwd=app_folder, capture_output=True, text=True, check=True)
                    self.log_output(pip_result.stdout, "info")
                    if pip_result.stderr:
                        self.log_output(f"Pip warnings/errors: {pip_result.stderr}", "error")
                    self.log_output("Dependencies installed successfully.", "success")
                except subprocess.CalledProcessError as e:
                    self.log_output(f"Error installing dependencies: {e.stderr}", "error")
                    self.status_message.set("Error installing dependencies.")
                    self.run_button.config(state=tk.NORMAL)
                    return
                except FileNotFoundError:
                    self.log_output("Error: 'pip' command not found. Ensure Python and pip are in your PATH.", "error")
                    self.status_message.set("Error: pip not found.")
                    self.run_button.config(state=tk.NORMAL)
                    return
            else:
                self.log_output("No requirements.txt found. Skipping dependency installation.", "info")

            # Determine the Flask app entry point
            # Prioritize FLASK_APP environment variable if set, otherwise default to common names
            flask_app_file = os.environ.get("FLASK_APP") # Check if FLASK_APP is already set in the environment
            if not flask_app_file:
                # Try common Flask app file names
                for f in ["app.py", "wsgi.py", "main.py"]:
                    if os.path.exists(os.path.join(app_folder, f)):
                        flask_app_file = f
                        break
            
            if not flask_app_file:
                self.log_output(f"Could not find a common Flask app file (e.g., app.py, wsgi.py, main.py) in {app_folder}. Please ensure your main Flask file is named one of these or set the FLASK_APP environment variable.", "error")
                self.status_message.set("Flask app file not found.")
                self.run_button.config(state=tk.NORMAL)
                return

            self.log_output(f"Using '{flask_app_file}' as the Flask application entry point.", "info")

            # Set FLASK_APP environment variable for the subprocess
            env = os.environ.copy()
            env["FLASK_APP"] = flask_app_file
            env["FLASK_ENV"] = "development" # Set development environment for more verbose output

            # Command to run Flask
            flask_cmd = [sys.executable, "-m", "flask", "run"]

            self.log_output(f"Running command: {' '.join(flask_cmd)}", "info")
            self.flask_process = subprocess.Popen(
                flask_cmd,
                cwd=app_folder,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, # Redirect stderr to stdout for easier logging
                text=True, # Decode output as text
                bufsize=1, # Line-buffered output
                universal_newlines=True, # Handle different newline characters
                env=env # Pass environment variables
            )

            self.master.after(100, lambda: self.stop_button.config(state=tk.NORMAL)) # Enable stop button after process starts

            # Read output line by line
            for line in iter(self.flask_process.stdout.readline, ''):
                self.log_output(line.strip())
                if "Running on http://" in line:
                    url = line.split("Running on ")[-1].strip().replace(" (Press CTRL+C to quit)", "")
                    self.status_message.set(f"Flask app running at: {url}")
                    self.log_output(f"Flask app is now accessible at: {url}", "success")

            # Wait for the process to terminate and get its return code
            return_code = self.flask_process.wait()
            self.log_output(f"Flask process exited with code: {return_code}", "info")
            if return_code != 0:
                self.status_message.set(f"Flask app stopped with error (Code: {return_code}). Check output for details.")
                self.log_output("Flask app terminated unexpectedly. Please check your Flask application's code for errors.", "error")
            else:
                self.status_message.set("Flask app stopped gracefully.")
                self.log_output("Flask app stopped.", "success")

        except Exception as e:
            self.log_output(f"An unexpected error occurred: {e}", "error")
            self.status_message.set("Error running Flask app.")
        finally:
            self.flask_process = None
            self.master.after(100, lambda: self.run_button.config(state=tk.NORMAL))
            self.master.after(100, lambda: self.stop_button.config(state=tk.DISABLED))


    def stop_flask_app(self):
        """Terminates the running Flask application process."""
        if self.flask_process and self.flask_process.poll() is None:
            self.log_output("Attempting to stop Flask app...", "info")
            self.status_message.set("Stopping Flask app...")
            try:
                # Terminate the process gracefully
                self.flask_process.terminate()
                # Wait a bit for it to terminate, then kill if it's still alive
                time.sleep(2)
                if self.flask_process.poll() is None:
                    self.flask_process.kill()
                self.log_output("Flask app stopped.", "success")
                self.status_message.set("Flask app stopped.")
            except Exception as e:
                self.log_output(f"Error stopping Flask app: {e}", "error")
                self.status_message.set("Error stopping Flask app.")
            finally:
                self.flask_process = None
                self.run_button.config(state=tk.NORMAL)
                self.stop_button.config(state=tk.DISABLED)
        else:
            messagebox.showinfo("Info", "No Flask app is currently running.")
            self.status_message.set("No Flask app running.")
            self.run_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)

    def on_closing(self):
        """Handles closing the application window."""
        if self.flask_process and self.flask_process.poll() is None:
            if messagebox.askyesno("Quit", "A Flask app is running. Do you want to stop it and quit?"):
                self.stop_flask_app()
                self.master.destroy()
            else:
                pass # Do nothing, keep the window open
        else:
            self.master.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = FlaskRunnerApp(root)
    root.mainloop()
