import tkinter as tk
import random
import math

BG = '#ff00fe'  # color magico -> transparente en Windows

W, H = 220, 240

PAL = dict(
    cuerpo='#F6C87E',   # dorado
    borde='#E3A94F',
    panza='#FFF6EC',
    rosa='#FFB7C5',
    rubor='#FFC9D4',
    ojo='#2B2228',
    boca='#C96A5B',
)

MOTIVACIONES = [
    '¡Eres increíble!',
    'Sigue así, campeón',
    'Hoy es un gran día',
    'Tú puedes con todo',
    'Brilla, que lo vales',
    'Descansa, te lo mereces',
    'Un paso a la vez, lo logras',
    'Eres más fuerte de lo que crees',
    'Cada día mejoras un poco más',
    'Sonríe, te ves genial',
]

MILESTONES = {
    5: '¡5 caricias! Eres muy cariñoso ♥',
    10: '¡10 caricias! Soy la mascota más feliz',
    25: '¡25 caricias! Me muero de amor',
    50: '¡50 caricias! Eres leyenda',
    100: '¡100 caricias! Nos vamos a vivir juntos',
}

REACCIONES = ['¡Mmm qué rico!', 'Me encanta esto', 'No pares nunca',
              'Soy feliz contigo', 'Purr...']

class Mascota:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('Mascota')
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        try:
            self.root.attributes('-transparentcolor', BG)
        except tk.TclError:
            pass

        self._cerrado = False
        self._tick = None
        self._sw = self.root.winfo_screenwidth()
        self._sh = self.root.winfo_screenheight()

        self.px = self._sw - W - 40
        self.py = self._sh - H - 60
        self.root.geometry(f'{W}x{H}+{self.px}+{self.py}')

        self.cv = tk.Canvas(self.root, width=W, height=H, bg=BG,
                            highlightthickness=0, bd=0)
        self.cv.pack(fill='both', expand=True)

        self.cx = W // 2
        self.g = H - 14
        self.estado = 'idle'   # idle | walk | sleep | eat | happy
        self.timer = 0
        self.parpadea = False
        self.cola_ang = 0.0
        self.target = None
        self.particulas = []
        self.corazones = []
        self.zzz = None
        self.zzz_age = 0
        self.estomago = 100
        self.arrastrando = False
        self.caricias = 0
        self._pet_call = None
        self.oy = 0
        self.prev_oy = 0
        self._boca_abierta = None

        self._dibujar()
        self._menus()
        self._bindings()
        self.bucle()
        try:
            self.root.mainloop()
        finally:
            self._cerrado = True
            self.root.destroy()

    # ---------- dibujo ----------
    def _dibujar(self):
        cv, x, g, P = self.cv, self.cx, self.g, PAL
        c, b = P['cuerpo'], P['borde']

        # colita diminuta (detras)
        self.cola = cv.create_oval(x+56, g-24, x+70, g-10,
                                   fill='white', outline=b, width=2)
        self._cola_base = (x+56, g-24, x+70, g-10)

        # orejitas redondas
        self.oizq = cv.create_oval(x-36, g-132, x-12, g-108, fill=c, outline=b, width=2)
        self.oizq_i = cv.create_oval(x-32, g-128, x-16, g-112, fill=P['rosa'], outline='')
        self.oder = cv.create_oval(x+12, g-132, x+36, g-108, fill=c, outline=b, width=2)
        self.oder_i = cv.create_oval(x+16, g-128, x+32, g-112, fill=P['rosa'], outline='')

        # cuerpo rechoncho
        self.cuerpo = cv.create_oval(x-58, g-110, x+58, g+8, fill=c, outline=b, width=3)
        self.brillo = cv.create_oval(x-44, g-100, x-18, g-82,
                                     fill='white', outline='', stipple='gray50')
        self.panza = cv.create_oval(x-34, g-46, x+34, g+4, fill=P['panza'], outline='')

        # cachetes (abazones) blancos
        self.mej_l = cv.create_oval(x-52, g-78, x-14, g-32, fill=P['panza'], outline='')
        self.mej_r = cv.create_oval(x+14, g-78, x+52, g-32, fill=P['panza'], outline='')
        # rubor dentro de los cachetes
        self.meji = cv.create_oval(x-42, g-66, x-26, g-50, fill=P['rubor'], outline='')
        self.mejd = cv.create_oval(x+26, g-66, x+42, g-50, fill=P['rubor'], outline='')

        # ojos grandes y brillantes
        self.ojo_i = cv.create_oval(x-24, g-94, x-6, g-78, fill=P['ojo'])
        self.ojo_d = cv.create_oval(x+6, g-94, x+24, g-78, fill=P['ojo'])
        self.bri_i = cv.create_oval(x-20, g-91, x-13, g-84, fill='white', outline='')
        self.bri_d = cv.create_oval(x+13, g-91, x+20, g-84, fill='white', outline='')
        self.bri2_i = cv.create_oval(x-9, g-81, x-6, g-78, fill='white', outline='')
        self.bri2_d = cv.create_oval(x+6, g-81, x+9, g-78, fill='white', outline='')
        # parpados cerrados
        self.pil = cv.create_arc(x-25, g-93, x-5, g-77, start=180, extent=180,
                                 style='arc', outline=P['ojo'], width=3, state='hidden')
        self.pid = cv.create_arc(x+5, g-93, x+25, g-77, start=180, extent=180,
                                 style='arc', outline=P['ojo'], width=3, state='hidden')

        # nariz y boca
        self.nariz = cv.create_polygon(x-3, g-73, x+3, g-73, x, g-67,
                                       fill='#E88A9A', outline='')
        self.boca = cv.create_line(x-5, g-66, x-2, g-63, x, g-66,
                                   x+2, g-63, x+5, g-66,
                                   smooth=True, fill=P['boca'], width=2)
        self.boca_feliz = cv.create_arc(x-9, g-72, x+9, g-54, start=180, extent=180,
                                        style='pieslice', outline=P['boca'],
                                        fill='#F06B79', state='hidden')
        # bigotes
        bs = [(x-16, g-62, x-44, g-68), (x-16, g-56, x-44, g-56), (x-16, g-50, x-44, g-44),
              (x+16, g-62, x+44, g-68), (x+16, g-56, x+44, g-56), (x+16, g-50, x+44, g-44)]
        self.big = [cv.create_line(*p, fill='#C9C0B8', width=1) for p in bs]

        # patitas delante (juntas)
        self.pata_i = cv.create_oval(x-13, g-34, x-2, g-20, fill=P['panza'], outline=b, width=2)
        self.pata_d = cv.create_oval(x+2, g-34, x+13, g-20, fill=P['panza'], outline=b, width=2)

        # base / peana
        self.base_l = cv.create_oval(x-46, g+2, x+46, g+18, fill='#B9A8D8', outline='')
        self.base_s = cv.create_oval(x-46, g-4, x+46, g+10, fill='#E8E0F0',
                                     outline='#C9B8E0', width=2)

        # collar con campanita
        self.collar = cv.create_oval(x-26, g-46, x+26, g-30,
                                     fill='#FF7FA0', outline='#E05A80', width=2)
        self.argolla = cv.create_oval(x-3, g-34, x+3, g-28, fill='#C9A000', outline='')
        self.campana = cv.create_oval(x-8, g-26, x+8, g-12,
                                      fill='#FFD700', outline='#C9A000', width=2)
        self.camp_i = cv.create_oval(x-3, g-20, x+3, g-15, fill='#C9A000', outline='')

        self.todo = [self.cola, self.oizq, self.oizq_i, self.oder, self.oder_i,
                     self.cuerpo, self.brillo, self.panza,
                     self.mej_l, self.mej_r, self.meji, self.mejd,
                     self.ojo_i, self.ojo_d, self.bri_i, self.bri_d,
                     self.bri2_i, self.bri2_d, self.pil, self.pid,
                     self.nariz, self.boca, self.boca_feliz,
                     *self.big, self.pata_i, self.pata_d,
                     self.base_l, self.base_s,
                     self.collar, self.argolla, self.campana, self.camp_i]

    # ---------- menus / eventos ----------
    def _menus(self):
        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label='♥ Caricias: 0', state='disabled')
        self.menu.add_separator()
        self.menu.add_command(label='Acariciar', command=self._hacer_caricias)
        self.menu.add_command(label='Dar de comer', command=lambda: self.cambiar('eat'))
        self.menu.add_command(label='Dormir', command=lambda: self.cambiar('sleep'))
        self.menu.add_command(label='Despertar', command=self.despertar)
        self.menu.add_command(label='Paseo', command=self.ir_a_pasear)
        self.menu.add_separator()
        self.menu.add_command(label='Salir', command=self._cerrar)

    def _bindings(self):
        self.cv.bind('<Button-1>', self.iniciar_arrastre)
        self.cv.bind('<B1-Motion>', self.mover_arrastre)
        self.cv.bind('<ButtonRelease-1>', self.soltar)
        self.cv.bind('<Button-3>', self.abrir_menu)
        self.cv.bind('<Double-Button-1>', self._doble)

    def abrir_menu(self, e):
        try:
            self.menu.tk_popup(e.x_root, e.y_root)
        finally:
            self.menu.grab_release()

    def _cancelar_pet(self):
        if self._pet_call is not None:
            try:
                self.root.after_cancel(self._pet_call)
            except tk.TclError:
                pass
            self._pet_call = None

    def iniciar_arrastre(self, e):
        self._cancelar_pet()
        self._press_x, self._press_y = e.x_root, e.y_root
        self.arrastrando = True
        self._dx = int(e.x_root - self.px)
        self._dy = int(e.y_root - self.py)

    def mover_arrastre(self, e):
        if not self.arrastrando:
            return
        # mantener dentro de la pantalla (nunca perder la mascota)
        self.px = int(max(-W + 40, min(e.x_root - self._dx, self._sw - 20)))
        self.py = int(max(0, min(e.y_root - self._dy, self._sh - 20)))
        self.root.geometry(f'+{self.px}+{self.py}')

    def soltar(self, e):
        self.arrastrando = False
        # clic corto (sin mover) = acariciar
        if (abs(e.x_root - self._press_x) <= 6 and
                abs(e.y_root - self._press_y) <= 6):
            self._cancelar_pet()
            # margen para no chocar con un doble clic
            self._pet_call = self.root.after(220, self._hacer_caricias)

    def _doble(self, e):
        self._cancelar_pet()
        self.cambiar('happy')

    def _cerrar(self):
        if self._cerrado:
            return
        self._cerrado = True
        self._cancelar_pet()
        try:
            if self._tick is not None:
                self.root.after_cancel(self._tick)
        except tk.TclError:
            pass
        self.root.destroy()

    # ---------- expresiones ----------
    def _ojos(self, cerrados):
        st = 'hidden' if cerrados else 'normal'
        for it in (self.ojo_i, self.ojo_d, self.bri_i, self.bri_d,
                   self.bri2_i, self.bri2_d):
            self.cv.itemconfigure(it, state=st)
        stc = 'normal' if cerrados else 'hidden'
        self.cv.itemconfigure(self.pil, state=stc)
        self.cv.itemconfigure(self.pid, state=stc)

    def _boca(self, abierta):
        if abierta == self._boca_abierta:
            return
        self._boca_abierta = abierta
        if abierta:
            self.cv.itemconfigure(self.boca, state='hidden')
            self.cv.itemconfigure(self.boca_feliz, state='normal')
        else:
            self.cv.itemconfigure(self.boca, state='normal')
            self.cv.itemconfigure(self.boca_feliz, state='hidden')

    def cambiar(self, estado):
        if self._cerrado:
            return
        if estado != 'pet':
            self.cv.delete('mano')
        self.estado = estado
        self.timer = 0
        if estado == 'eat':
            self.hablar(random.choice(['¡Ñam ñam!', '¡Qué rico!', 'Mmm...']))
            self._comida()
        elif estado == 'happy':
            self.hablar(random.choice(['¡Hola!', 'Me gustas', '¡Squeak!']))
            for _ in range(4):
                self._corazon()
        elif estado == 'sleep':
            self.cv.delete('bocadillo')
            self._ojos(True)

    def despertar(self):
        if self._cerrado:
            return
        self.estado = 'idle'
        self.timer = 0
        self._ojos(False)
        self.cv.delete('zzz')
        self.zzz = None

    def ir_a_pasear(self):
        self.target = (random.randint(20, max(21, self._sw - W - 20)),
                       random.randint(40, max(41, self._sh - H - 20)))
        self.estado = 'walk'
        self.timer = 0

    # ---------- caricias ----------
    def _hacer_caricias(self):
        if self._cerrado:
            return
        self._pet_call = None
        self.caricias += 1
        self.estado = 'pet'
        self.timer = 0
        self.parpadea = False
        self._boca_abierta = None
        self._ojos(True)          # ojos cerrados de felicidad
        self._crear_mano()
        try:
            self.menu.entryconfigure(0, label=f'♥ Caricias: {self.caricias}')
        except tk.TclError:
            pass
        self.cv.delete('bocadillo')
        msg = (MILESTONES.get(self.caricias)
               or (random.choice(MOTIVACIONES) if self.caricias % 5 == 0
                   else random.choice(REACCIONES)))
        self.hablar(msg)

    def _crear_mano(self):
        cv, x = self.cv, self.cx
        hy = self.g - 122
        self._mano_base = (x, hy)
        self.mano_c = cv.create_rectangle(x-14, hy-8, x+14, hy+12,
                                          fill='#FFE0F0', outline='#D9A8C2',
                                          width=2, tags='mano')
        self.mano_p = cv.create_oval(x-16, hy+8, x+16, hy+28,
                                     fill='#FFE0F0', outline='#D9A8C2',
                                     width=2, tags='mano')

    def _animar_mano(self):
        if self.estado != 'pet':
            return
        cv = self.cv
        xo = math.sin(self.timer * 0.35) * 34
        bx, hy = self._mano_base
        cv.coords(self.mano_c, bx+xo-14, hy-8, bx+xo+14, hy+12)
        cv.coords(self.mano_p, bx+xo-16, hy+8, bx+xo+16, hy+28)
        if self.timer % 4 == 0 and random.random() < 0.6:
            self._corazon()

    # ---------- extras ----------
    def hablar(self, texto):
        self.cv.delete('bocadillo')
        bx, by, bw, bh = 26, 6, 168, 46
        self.cv.create_oval(bx, by, bx+bw, by+bh, fill='white',
                            outline='#F0C6D8', width=2, tags='bocadillo')
        self.cv.create_polygon(bx+bw//2-9, by+bh-2, bx+bw//2+9, by+bh-2,
                               bx+bw//2, by+bh+14, fill='white', tags='bocadillo')
        self.cv.create_text(bx+bw//2, by+bh//2, text=texto, width=bw-18,
                            font=('Segoe UI', 9), fill='#6B4F5A',
                            justify='center', tags='bocadillo')

    def _comida(self):
        cv, x, g = self.cv, self.cx, self.g
        cv.create_oval(x-34, g+0, x+34, g+22, fill='#FFE0B2',
                       outline='#E0A75F', width=2, tags='comida')
        fy = g + 8
        cv.create_polygon(x-18, fy, x-4, fy-6, x-4, fy+6,
                          fill='#FF9AA2', outline='#E07A82', tags='comida')
        cv.create_polygon(x+4, fy, x+14, fy-4, x+14, fy+4,
                          fill='#FF9AA2', outline='#E07A82', tags='comida')
        cv.create_oval(x+10, fy-2, x+13, fy+1, fill='white', outline='', tags='comida')

    def _corazon(self):
        if self._cerrado:
            return
        pid = self.cv.create_text(self.cx + random.randint(-34, 34),
                                  self.g - random.randint(60, 100), text='♥',
                                  font=('Segoe UI', 18),
                                  fill=random.choice(['#FF6B9D', '#FF8FAB', '#F8A1D1']),
                                  tags='corazon')
        self.corazones.append([pid, 0])

    def _nueva_particula(self):
        colores = ['#FFD1DC', '#FFFACD', '#C9F7F5', '#DCD0FF', '#BFFCC6', '#FFE9A8']
        x, y = random.randint(12, W-12), random.randint(14, H-150)
        pid = self.cv.create_polygon(
            x, y-6, x+3, y-1, x+6, y, x+3, y+1, x, y+6, x-3, y+1, x-6, y, x-3, y-1,
            fill=random.choice(colores), outline='', tags='particula')
        self.particulas.append([x, y, 0, pid])

    # ---------- bucle ----------
    def bucle(self):
        if self._cerrado:
            return
        self.timer += 1
        try:
            if not self.arrastrando:
                self._logica()
            self._animar()
        except tk.TclError:
            self._cerrado = True
            return
        try:
            self._tick = self.root.after(80, self.bucle)
        except tk.TclError:
            self._cerrado = True

    def _logica(self):
        e = self.estado
        if e == 'walk':
            if self.target is None:
                self.estado = 'idle'
                return
            dx = self.target[0] - self.px
            dy = self.target[1] - self.py
            d = math.hypot(dx, dy)
            if d < 6:
                self.target = None
                self.estado = 'idle'
                self.oy = 0
                return
            self.px = int(self.px + dx / d * 3)
            self.py = int(self.py + dy / d * 3)
            self.root.geometry(f'+{self.px}+{self.py}')
            self.oy = 5 if (self.timer // 2) % 2 else 0
        elif e == 'eat':
            if self.timer == 1:
                self.estomago = min(100, self.estomago + 30)
            if self.timer > 30:
                self.estado = 'happy'
                self.timer = 0
                self.cv.delete('comida')
        elif e == 'happy':
            if self.timer == 20:
                self.estado = 'idle'
                self.timer = 0
        elif e == 'sleep':
            if self.timer % 16 == 0:
                self.cv.delete('zzz')
                self.zzz = self.cv.create_text(
                    self.cx + 48, 62, text='z' * (1 + (self.timer // 16) % 3),
                    font=('Segoe UI', 15, 'bold'), fill='#8FBCFF', tags='zzz')
                self.zzz_age = 0
        elif e == 'pet':
            self.oy = 2 if (self.timer // 2) % 2 else 4   # rebote feliz
            if self.timer > 22:
                self.estado = 'idle'
                self.timer = 0
                self.oy = 0
                self.cv.delete('mano')
                self._ojos(False)
        else:  # idle
            if self.estomago < 40 and self.timer % 120 == 0:
                self.hablar(random.choice(['Tengo hambre...', 'Ñam ñam?']))
            elif self.timer % 240 == 0 and random.random() < 0.35:
                if self.caricias > 0 and random.random() < 0.5:
                    self.hablar(random.choice(MOTIVACIONES))
                else:
                    self.hablar(random.choice(['Squeak~', '¡Hola humano!', '¿Me acaricias?', '...']))
            elif self.timer % 90 == 0:
                self.cv.delete('bocadillo')
            self.oy = 1 if (self.timer // 3) % 2 else 0   # respirar
            if self.timer % 400 == 0 and random.random() < 0.6:
                self.ir_a_pasear()

    def _animar(self):
        cv = self.cv
        # parpadeo
        if self.estado != 'sleep':
            if not self.parpadea and random.random() < 0.028:
                self.parpadea = True
                self._ojos(True)
            elif self.parpadea and random.random() < 0.2:
                self.parpadea = False
                self._ojos(False)
        # balanceo
        delta = self.oy - self.prev_oy
        if delta:
            cv.move(self.todo, 0, delta)
        self.prev_oy = self.oy
        # colita
        self.cola_ang += 0.15 if self.estado != 'sleep' else 0.03
        a = self.cola_ang
        if self.estado == 'happy':
            a = self.timer * 0.8
        osc = math.sin(a) * 5
        bx = self._cola_base
        cv.coords(self.cola, bx[0]+osc, bx[1], bx[2]+osc, bx[3])
        # boca
        self._boca(self.estado in ('happy', 'eat'))
        # zzz flotando
        if self.estado == 'sleep' and self.zzz is not None:
            self.zzz_age += 1
            cv.move(self.zzz, 0, -0.5)
            if self.zzz_age > 14:
                cv.delete(self.zzz)
                self.zzz = None
        # mano acariciando la cabeza
        self._animar_mano()
        # particulas
        for p in self.particulas:
            p[1] -= 1.1
            p[2] += 1
            if p[2] > 45:
                cv.delete(p[3])
                continue
            x, y = p[0], p[1]
            cv.coords(p[3], x, y-6, x+3, y-1, x+6, y, x+3, y+1,
                      x, y+6, x-3, y+1, x-6, y, x-3, y-1)
        self.particulas = [p for p in self.particulas if p[2] <= 45]
        if len(self.particulas) < 5 and random.random() < 0.015:
            self._nueva_particula()
        # corazones
        for c in self.corazones:
            cv.move(c[0], 0, -1.2)
            c[1] += 1
            if c[1] > 34:
                cv.delete(c[0])
        self.corazones = [c for c in self.corazones if c[1] <= 34]

if __name__ == '__main__':
    Mascota()