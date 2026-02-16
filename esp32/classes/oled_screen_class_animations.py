   # Draw a simple progress bar at the bottom (0 to 100 percent).
    def draw_progress(self, percent, y=54, height=8):
        # Clamp input so math stays safe
        if percent < 0:
            percent = 0
        if percent > 100:
            percent = 100

        # Outline of the bar
        self.oled.rect(0, y, self.width, height, 1)

        # Fill amount based on percent (leave 1px border on each side)
        fill_width = int((self.width - 2) * (percent / 100))
        if fill_width > 0:
            self.oled.fill_rect(1, y + 1, fill_width, height - 2, 1)

        self.oled.show()

    # Animate a progress bar from 0 to 100 (simple loading animation for demos).
    def animate_progress(self, step=10, delay_ms=120, y=54, height=8):
        # Clear once and keep drawing only the bar region over time
        self.oled.fill(0)
        self.oled.show()

        # Draw the bar increasing in steps
        for p in range(0, 101, step):
            self.oled.fill(0)
            self.draw_progress(p, y=y, height=height)
            time.sleep_ms(delay_ms)

    # Animate a tiny dot bouncing left-right (super cheap CPU animation for testing refresh).
    def bounce_dot(self, y=32, speed_ms=15, loops=2):
        # Use a 2x2 pixel dot so it is visible
        dot_size = 2

        # Move dot across and back a few times
        for _ in range(loops):
            for x in range(0, self.width - dot_size):
                self.oled.fill(0)
                self.oled.fill_rect(x, y, dot_size, dot_size, 1)
                self.oled.show()
                time.sleep_ms(speed_ms)

            for x in range(self.width - dot_size - 1, -1, -1):
                self.oled.fill(0)
                self.oled.fill_rect(x, y, dot_size, dot_size, 1)
                self.oled.show()
                time.sleep_ms(speed_ms)