import pygame
import colorsys

def climp(value, min, max):
    if value < min:
        return min
    elif value > max:
        return max
    else:
        return value

# Iniciar o Pygame
pygame.init()

# Criar uma janela
janela = pygame.display.set_mode((255 * 3, 255 * 3))

camada = 0
velocidade = 0

# Loop principal
while True:
    # Limpar a tela
    janela.fill((0, 0, 0))

    # Desenhar os quadrados
    for i in range(255):
        for j in range(255):
            h, l, s = colorsys.rgb_to_hls(camada, i+0.001, j+0.001)
            #ROSA: if h>0.79 and h < 0.94 and s < -0.2 and l> 15:
            if h>0.76 and h < 0.94 and s < -0.2 and l> 15:
                pygame.draw.rect(janela, (camada, i, j), (i * 3, j * 3, 3, 3)) # quanto mais pra direita, mais verde, mais pra baixo, mais azul
            else:
                pygame.draw.rect(janela, (0,0,0), (i * 3, j * 3, 3, 3))

    # Desenhar o texto
    font = pygame.font.SysFont("Arial", 32)
    x, y = pygame.mouse.get_pos()
    texto = f"R: {camada} G: {x//3} B: {y//3}"
    text = font.render(texto, True, (255, 255, 255))
    janela.blit(text, (0, 0))
    h, l, s = colorsys.rgb_to_hls(camada, x//3, y//3)
    texto = f"H: {round(h,4)} L: {l} S: {round(s,3)}"
    text = font.render(texto, True, (255, 255, 255))
    janela.blit(text, (0, 32))

    # Atualizar a tela
    pygame.display.update()
    camada = climp(camada + velocidade*3, 0, 255)
    

    # Tratar eventos
    for evento in pygame.event.get():
        if evento.type == pygame.QUIT:
            pygame.quit()
            exit()

        # Tratar eventos de teclado
        if evento.type == pygame.KEYDOWN:
            if evento.key == pygame.K_UP:
                velocidade += 1
            elif evento.key == pygame.K_DOWN:
                velocidade -= 1
        if evento.type == pygame.KEYUP:
            if evento.key == pygame.K_UP:
                velocidade -= 1
            elif evento.key == pygame.K_DOWN:
                velocidade += 1

