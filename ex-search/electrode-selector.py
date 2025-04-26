
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
import math

# Load the image
image_path = "net.png"  # Update with the correct path
img = Image.open(image_path)
img = img.resize((800, 800), Image.Resampling.LANCZOS)  # Resize image if necessary

# Manually define the coordinates for each electrode
electrode_positions = {
    'C5': (398, 262), 'T7': (328, 390), 'CP5': (358, 313), 'P9': (212, 493),
    'P7': (286, 486), 'P5': (342, 456), 'PO7': (388, 534), 'PO3': (444, 547),
    'O1': (498, 580), 'O2': (573, 580), 'PO4': (618, 547), 'PO8': (674, 534),
    # Add the coordinates for all other electrodes here...
}

class ElectrodeSelector(tk.Tk):
    def __init__(self, img, electrode_positions):
        super().__init__()
        self.title("Electrode Selector")

        self.img = ImageTk.PhotoImage(img)
        
        # Create frames
        self.image_frame = tk.Frame(self)
        self.image_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.info_frame = tk.Frame(self)
        self.info_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(self.image_frame, width=img.width, height=img.height)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.img)
        self.canvas.bind("<Button-1>", self.on_click)

        self.selected_electrodes = []
        self.electrode_positions = electrode_positions

        # Create mode selection dropdown
        self.mode_var = tk.StringVar(value="Unipolar")
        self.mode_menu = tk.OptionMenu(self.info_frame, self.mode_var, "Unipolar", "Multipolar", command=self.update_mode)
        self.mode_menu.pack()

        # Create multipolar count dropdown (hidden by default)
        self.multipolar_count_var = tk.StringVar(value="4")
        self.multipolar_count_menu = tk.OptionMenu(self.info_frame, self.multipolar_count_var, "4", "6", "8", command=self.update_multipolar)
        self.multipolar_count_menu.pack()
        self.multipolar_count_menu.pack_forget()

        # Frame for radio buttons
        self.radio_buttons_frame = tk.Frame(self.info_frame)
        self.radio_buttons_frame.pack()

        # Create a frame for the text widgets
        self.text_frames_container = tk.Frame(self.info_frame)
        self.text_frames_container.pack(fill=tk.BOTH, expand=True)

        # Create text widgets for each selector
        self.text_frames = {}
        self.create_unipolar_selectors()

        self.done_button = tk.Button(self.info_frame, text="Done", command=self.on_done)
        self.done_button.pack()

    def create_unipolar_selectors(self):
        self.clear_selectors()
        self.selector_var = tk.StringVar(value="E1+")
        self.create_radio_button("E1+", "E1+")
        self.create_radio_button("E1-", "E1-")
        self.create_radio_button("E2+", "E2+")
        self.create_radio_button("E2-", "E2-")
        self.arrange_text_widgets()

    def create_multipolar_selectors(self, count):
        self.clear_selectors()
        self.selector_var = tk.StringVar(value="E1+")
        for i in range(1, int(count) + 1):
            self.create_radio_button(f"E{i}+", f"E{i}+")
            self.create_radio_button(f"E{i}-", f"E{i}-")
        self.arrange_text_widgets()

    def create_radio_button(self, text, value):
        radio_button = tk.Radiobutton(self.radio_buttons_frame, text=text, variable=self.selector_var, value=value)
        radio_button.pack(side=tk.LEFT)

        frame = tk.Frame(self.text_frames_container)
        label = tk.Label(frame, text=value)
        label.pack()
        text_widget = tk.Text(frame, height=5, width=20)  # Adjusted size for compactness
        text_widget.pack()
        self.text_frames[value] = text_widget

    def arrange_text_widgets(self):
        for i, (key, text_widget) in enumerate(self.text_frames.items()):
            row = i % 4
            col = i // 4
            text_widget.master.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
        for col in range((len(self.text_frames) + 3) // 4):  # Ensure all columns expand equally
            self.text_frames_container.columnconfigure(col, weight=1)

    def clear_selectors(self):
        for widget in self.radio_buttons_frame.winfo_children():
            widget.destroy()
        for frame in self.text_frames_container.winfo_children():
            frame.destroy()
        self.text_frames.clear()

    def on_click(self, event):
        x, y = event.x, event.y
        closest_electrode = self.find_closest_electrode(x, y)
        if closest_electrode:
            selector = self.selector_var.get()
            self.selected_electrodes.append((x, y, closest_electrode, selector))
            self.mark_electrode(x, y, selector)
            self.update_info(closest_electrode, selector)

    def find_closest_electrode(self, x, y):
        closest_electrode = None
        min_distance = float('inf')
        for electrode, (ex, ey) in self.electrode_positions.items():
            distance = math.sqrt((ex - x) ** 2 + (ey - y) ** 2)
            if distance < min_distance:
                min_distance = distance
                closest_electrode = electrode
        return closest_electrode

    def mark_electrode(self, x, y, selector):
        radius = 15  # Increased radius for larger circles
        color = self.get_color(selector)
        self.canvas.create_oval(x - radius, y - radius, x + radius, y + radius, outline=color, width=3)

    def update_info(self, electrode, selector):
        text_widget = self.text_frames[selector]
        text_widget.insert(tk.END, f"{electrode}\n")
        text_widget.see(tk.END)

    def get_color(self, selector):
        colors = {
            "E1+": "red",
            "E1-": "green",
            "E2+": "blue",
            "E2-": "yellow",
            "E3+": "purple",
            "E3-": "orange",
            "E4+": "cyan",
            "E4-": "magenta",
            "E5+": "brown",
            "E5-": "pink",
            "E6+": "gray",
            "E6-": "lime",
            "E7+": "olive",
            "E7-": "navy",
            "E8+": "teal",
            "E8-": "maroon"
        }
        return colors.get(selector, "black")

    def update_mode(self, mode):
        if mode == "Unipolar":
            self.multipolar_count_menu.pack_forget()
            self.create_unipolar_selectors()
        else:
            self.multipolar_count_menu.pack()

    def update_multipolar(self, count):
        self.create_multipolar_selectors(count)

    def on_done(self):
        self.destroy()

if __name__ == "__main__":
    app = ElectrodeSelector(img, electrode_positions)
    app.mainloop()

