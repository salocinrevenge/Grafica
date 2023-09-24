from PIL import Image
import os
import numpy as np
from sklearn.cluster import DBSCAN
from tqdm import tqdm
import colorsys


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
        analises = {"rosa": ((0.94, 0.75, -0.1, 150), (10, 100))}
        
        '''
        0.94 > h > 0.75 and s < -0.2 and l> 15:
        '''
    
        num_polens_encontrados = []
        # executa todas analises
        for key in analises:

            

            binary_array_hsl = np.full(img_np.shape[:-1], False)

            print("vou converter imagem")
            for i in range(img_np.shape[0]):
                for j in range(img_np.shape[1]):
                    h,l,s = colorsys.rgb_to_hls(img_np[i][j][0]+0.0001, img_np[i][j][1]+0.0001, img_np[i][j][2]+0.0001)
                    if  analises[key][0][0] > h > analises[key][0][1] and s < analises[key][0][2] and l> analises[key][0][3]:
                        binary_array_hsl[i][j] = True
            print("imagem hsl criada")

            # Contando o numero de grupos com DBSCAN
            # Obter as coordenadas dos pontos brancos (True) no vetor binário
            white_points = np.argwhere(binary_array_hsl)
            if len(white_points) == 0:
                    num_polens_encontrados.append(0)
                    continue
            # Executar o algoritmo DBSCAN
            dbscan = DBSCAN(eps=analises[key][1][0], min_samples=analises[key][1][1])   # analises[key][2] eh uma tupla contendo ambos hiperparametros
            labels = dbscan.fit_predict(white_points)
            num_polens_encontrados.append(labels.max()+1)
        if len(set(num_polens_encontrados)) == 0:
            relatar = f'{filename.replace(".tif","")}: Erro! Tamanho de num_polens_encontrado nulo'
        else:
            relatar = f'{filename.replace(".tif","")}: {num_polens_encontrados}'
        # Escrevendo o resultado no arquivo de saída "polens.txt"
        with open("polens.txt", "a") as file:
            file.write(relatar + "\n")

                


