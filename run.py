from PIL import Image
import os
import numpy as np
from sklearn.cluster import DBSCAN
from tqdm import tqdm


folder = input("insira o caminho para a pasta com as imagens: ")  # exemplo: imagens/ ou o caminho completo absoluto

saidas = []
for filename in tqdm(sorted(os.listdir(folder)), desc="arquivos analisados" ):
    if filename.endswith(".tif"):
        img_path = os.path.join(folder, filename)
        img = Image.open(img_path)
        img_np = np.array(img) # numpy da imagem, tridimensional

        """
        o dicionario abaixo armazena todas as informacoes para a execucao do codigo com seus parametros:
        a chave representa o nome da analise, aqui nomeei por centro e borda, podendo adicionar mais
        tipos de analises. O elemento salvo eh uma tupla com um numpy array do codigo da cor analisada;
        um numero contendo a distancia ate a cor de refencia para ainda ser considerado polen;
        uma segunda tupla contendo os parametros para o dbscan no formato (epsilon, min_samples)
        epsilon representa o raio da vizinhanca e min samples o numero minimo de amostras para formar
        um cluster. Lembrando que esses parametros sao experimentais, e podem ser obtidos analisando
        no notebook desse git com a imagem desejada.
        """
        analises = {"centro": (np.array([186, 139, 157]), 15, (20, 80)), "borda": (np.array([255,161,247]), 50,(40,20)), "centro_claro": (np.array([169,99,173]), 30, (40, 80))}
    
        num_polens_encontrados = []
        # executa todas analises
        for key in analises:
            # Calcular a distância euclidiana para cada ponto da imagem
            distances_center = np.linalg.norm(img_np - analises[key][0], axis=2) # analises[key][0]: cor de referencia em np

            # Criar um vetor binário baseado na distância euclidiana
            binary_array_center = distances_center < analises[key][1] # analises[key][1]: distancia maxima ate cor de referencia

            # Contando o numero de grupos com DBSCAN
            # Obter as coordenadas dos pontos brancos (True) no vetor binário
            white_points = np.argwhere(binary_array_center)
            if len(white_points) == 0:
                    num_polens_encontrados.append(0)
                    continue
            # Executar o algoritmo DBSCAN
            dbscan = DBSCAN(eps=analises[key][2][0], min_samples=analises[key][2][1])   # analises[key][2] eh uma tupla contendo ambos hiperparametros
            labels = dbscan.fit_predict(white_points)
            num_polens_encontrados.append(labels.max()+1)
        if len(set(num_polens_encontrados)) == 0:
            relatar = f'{filename.replace(".tif","")}: Erro! Tamanho de num_polens_encontrado nulo'
        else:
            relatar = f'{filename.replace(".tif","")}: {num_polens_encontrados}'
        # Escrevendo o resultado no arquivo de saída "polens.txt"
        with open("polens.txt", "a") as file:
            file.write(relatar + "\n")

                


