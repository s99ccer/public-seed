import tkinter as tk
import random

COLS, ROWS = 10, 20
CELL = 30
W = COLS * CELL
H = ROWS * CELL

SHAPES = [
    [[1,1,1,1]],
    [[1,1],[1,1]],
    [[0,1,0],[1,1,1]],
    [[0,1,1],[1,1,0]],
    [[1,1,0],[0,1,1]],
    [[1,0,0],[1,1,1]],
    [[0,0,1],[1,1,1]],
]

COLORS = ["cyan", "yellow", "purple", "green", "red", "blue", "orange"]

class Tetris:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Tetris")
        self.root.resizable(False, False)

        self.canvas = tk.Canvas(self.root, width=W+200, height=H, bg="black")
        self.canvas.pack()

        self.board = [[0]*COLS for _ in range(ROWS)]
        self.score = 0
        self.game_over = False

        self.current = self.new_piece()
        self.next = self.new_piece()

        self.drop_counter = 0
        self.drop_speed = 30

        self.root.bind("<Left>", lambda e: self.move(-1, 0))
        self.root.bind("<Right>", lambda e: self.move(1, 0))
        self.root.bind("<Down>", lambda e: self.move(0, 1))
        self.root.bind("<Up>", lambda e: self.rotate())
        self.root.bind("<space>", lambda e: self.hard_drop())

        self.draw()
        self.root.after(50, self.update)
        self.root.mainloop()

    def new_piece(self):
        idx = random.randrange(len(SHAPES))
        shape = [row[:] for row in SHAPES[idx]]
        return {"shape": shape, "x": COLS//2 - len(shape[0])//2, "y": 0, "color": COLORS[idx]}

    def valid(self, shape, x, y):
        for r in range(len(shape)):
            for c in range(len(shape[0])):
                if shape[r][c]:
                    cx, cy = x + c, y + r
                    if cx < 0 or cx >= COLS or cy >= ROWS or cy < 0:
                        return False
                    if cy >= 0 and self.board[cy][cx]:
                        return False
        return True

    def lock(self):
        p = self.current
        for r in range(len(p["shape"])):
            for c in range(len(p["shape"][0])):
                if p["shape"][r][c]:
                    cy = p["y"] + r
                    cx = p["x"] + c
                    if cy >= 0:
                        self.board[cy][cx] = p["color"]
        self.clear_lines()
        self.current = self.next
        self.next = self.new_piece()
        if not self.valid(self.current["shape"], self.current["x"], self.current["y"]):
            self.game_over = True

    def clear_lines(self):
        new_board = [row for row in self.board if any(c == 0 for c in row)]
        cleared = ROWS - len(new_board)
        self.score += cleared * 100
        self.board = [[0]*COLS for _ in range(cleared)] + new_board

    def move(self, dx, dy):
        if self.game_over:
            return
        p = self.current
        if self.valid(p["shape"], p["x"]+dx, p["y"]+dy):
            p["x"] += dx
            p["y"] += dy
        elif dy == 1:
            self.lock()
        self.draw()

    def rotate(self):
        if self.game_over:
            return
        p = self.current
        shape = list(zip(*p["shape"][::-1]))
        shape = [list(row) for row in shape]
        if self.valid(shape, p["x"], p["y"]):
            p["shape"] = shape
        self.draw()

    def hard_drop(self):
        if self.game_over:
            return
        p = self.current
        while self.valid(p["shape"], p["x"], p["y"]+1):
            p["y"] += 1
        self.lock()
        self.draw()

    def update(self):
        if not self.game_over:
            self.drop_counter += 1
            if self.drop_counter >= self.drop_speed:
                self.move(0, 1)
                self.drop_counter = 0
        self.root.after(50, self.update)

    def draw(self):
        self.canvas.delete("all")

        for r in range(ROWS):
            for c in range(COLS):
                if self.board[r][c]:
                    self.draw_cell(c, r, self.board[r][c])

        p = self.current
        for r in range(len(p["shape"])):
            for c in range(len(p["shape"][0])):
                if p["shape"][r][c]:
                    self.draw_cell(p["x"]+c, p["y"]+r, p["color"])

        for r in range(ROWS):
            self.canvas.create_line(0, r*CELL, W, r*CELL, fill="#333")
        for c in range(COLS+1):
            self.canvas.create_line(c*CELL, 0, c*CELL, H, fill="#333")

        ox, oy = W + 30, 50
        self.canvas.create_text(ox+45, 20, text="NEXT", fill="white", font=("Arial", 14))
        n = self.next
        for r in range(len(n["shape"])):
            for c in range(len(n["shape"][0])):
                if n["shape"][r][c]:
                    x = ox + c * CELL
                    y = oy + r * CELL
                    self.canvas.create_rectangle(x, y, x+CELL, y+CELL, fill=n["color"], outline="gray")

        self.canvas.create_text(ox+45, 200, text="SCORE", fill="white", font=("Arial", 14))
        self.canvas.create_text(ox+45, 230, text=str(self.score), fill="white", font=("Arial", 20))

        if self.game_over:
            self.canvas.create_text(W//2, H//2, text="GAME OVER", fill="red", font=("Arial", 30, "bold"))

    def draw_cell(self, c, r, color):
        x, y = c*CELL, r*CELL
        self.canvas.create_rectangle(x, y, x+CELL, y+CELL, fill=color, outline="gray")
        self.canvas.create_rectangle(x+2, y+2, x+CELL-2, y+CELL-2, fill=color, outline="white")

if __name__ == "__main__":
    Tetris()
