#importando as bibliotecas
import cv2
import os
import pypdf
import PyPDF2
import pyttsx3
import time
import threading
import mediapipe as mp
import numpy as np
import speech_recognition as sr
import tkinter as tk
from PIL import Image, ImageTk
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from tkinter import filedialog, messagebox

#Configuração do reconhecimento de mãos
solucao_reconhecimento_maos = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils

#Ajustes para melhorar a precisão e fluidez
DETECTION_CONFIDENCE = 0.85
TRACKING_CONFIDENCE = 0.85
MIN_SIMILARIDADE = 0.9
TEMPO_MINIMO_ENTRE_DETECOES = 1.5 
TEMPO_MINIMO_FALA = 0.5 

#Controlador do loop da webcam
webcam_aberta = False
video_capture = None
webcam_label = None
texto_reconhecido = ""
engine = pyttsx3.init() 
rate = engine.getProperty('rate')
engine.setProperty('rate', rate - 50) 
ultimo_tempo_falado = {}

#Função p/selecionar o arquivo
def selecionar():
    global caminho
    caminho = filedialog.askopenfilename(filetypes=[("Arquivos PDF", "*.pdf")])
    if caminho:
        messagebox.showinfo("Sucesso", "Arquivo selecionado!")

#Função p/ler o arquivo
def ler():
    if not caminho:
        messagebox.showerror("Erro", "Nenhum arquivo PDF selecionado.")
        return
    with open(caminho, "rb") as arq:
        leitor = pypdf.PdfReader(arq)
        texto = ""

        for pg in leitor.pages:
            texto += pg.extract_text()

        engine.say(texto)
        engine.runAndWait()

#Função p/exibir as frases em imagens(libras)
def exibir_img():
    if not caminho:
        messagebox.showerror("Erro", "Nenhum arquivo PDF selecionado.")
        return

    with open(caminho, "rb") as arq:
        leitor = pypdf.PdfReader(arq)
        texto = ""
        # Extrai o texto de cada página e concatena (usando string vazia se None for retornado)
        for pg in leitor.pages:
            texto += (pg.extract_text() or "")
        # Converte o texto acumulado para maiúsculas
        texto = texto.upper()

        janela_img = tk.Toplevel()
        janela_img.title("LETRAS (LIBRAS)")

        frame_img = tk.Frame(janela_img)
        frame_img.pack()

        coluna = 0
        linha = 0
        img_linha = 16

        for letra in texto:
            if letra.isalpha():
                # Monta o caminho para a imagem na pasta "libras"
                nome_img = os.path.join("libras", f"{letra}.png")
                if os.path.exists(nome_img):
                    imagem = Image.open(nome_img)
                    imagem.thumbnail((100, 100))
                    imagem = ImageTk.PhotoImage(imagem)
                    label_imagem = tk.Label(frame_img, image=imagem)
                    label_imagem.image = imagem  # Mantém referência para evitar garbage collection
                    label_imagem.grid(row=linha, column=coluna, padx=5, pady=5)
                    coluna += 1
                    if coluna >= img_linha:
                        coluna = 0
                        linha += 1
            elif letra.isspace():
                espaco = tk.Label(frame_img, width=5)
                espaco.grid(row=linha, column=coluna, padx=5, pady=5)
                coluna += 1
                if coluna >= img_linha:
                    coluna = 0
                    linha += 1


#Função p/ converter áudio em texto
def conv_audio_texto():
    r = sr.Recognizer()
    with sr.Microphone() as source:
        try:
            print("Aguardando fala...")
            audio = r.listen(source, timeout=5)
            texto = r.recognize_google(audio, language="pt-BR")
            print("Você disse:", texto)
            return texto  # <- Essa linha é essencial para que o texto vá para a interface

        except sr.UnknownValueError:
            messagebox.showerror("Erro", "Não foi possível entender o áudio.")
            return None

        except sr.RequestError:
            messagebox.showerror("Erro", "Erro ao se comunicar com o serviço de reconhecimento.")
            return None

        except Exception as e:
            messagebox.showerror("Erro inesperado", str(e))
            return None
#Função p/definir a similaridade entre os videos e a imagem do usuário(a)
def calcular_similaridade_landmarks(landmarks_captados, landmarks_referencia):
    try:
        if landmarks_captados is None or landmarks_referencia is None:
            return 0
        if landmarks_captados.shape != landmarks_referencia.shape:
            return 0
        diferenca = np.linalg.norm(landmarks_captados - landmarks_referencia, axis=1)
        similaridade = 1 / (1 + np.mean(diferenca))
        return similaridade

    except Exception as e:
        print("Erro na comparação")
        return 0

#Função p/ extrair os dados que estão inclusos em cada gesto(landmarks)
def extrair_landmarks_video(caminho_video):
    landmarks_referencia = None
    try:
        imagem = cv2.imread(caminho_video)
        if imagem is None:
            print(f"Erro ao ler a imagem: {caminho_video}")
            return None
        frame_rgb = cv2.cvtColor(imagem, cv2.COLOR_BGR2RGB)
        with solucao_reconhecimento_maos.Hands(max_num_hands=1, min_detection_confidence=DETECTION_CONFIDENCE, min_tracking_confidence=TRACKING_CONFIDENCE) as hands:
            results = hands.process(frame_rgb)
            if results.multi_hand_landmarks:
                for hand_landmarks in results.multi_hand_landmarks:
                    pontos_mao = np.array([[lm.x, lm.y] for lm in hand_landmarks.landmark])
                    min_coords = np.min(pontos_mao, axis=0)
                    max_coords = np.max(pontos_mao, axis=0)
                    if np.all(max_coords > min_coords):
                        landmarks_referencia = (pontos_mao - min_coords) / (max_coords - min_coords)
                    else:
                        print(f"Erro: Coordenadas min e max são iguais para {caminho_video}")
                    break
    except Exception as e:
        print(f"Erro ao processar a imagem {caminho_video}: {e}")
    return landmarks_referencia

#Função p/ler o texto do PDF
def ler_pdf(caminho_pdf):
    texto = ""
    try:
        with open(caminho_pdf, 'rb') as arquivo_pdf:
            leitor_pdf = PyPDF2.PdfReader(arquivo_pdf)
            for pagina in leitor_pdf.pages:
                texto += pagina.extract_text()

    except FileNotFoundError:
        print(f"Arquivo PDF não encontrado: {caminho_pdf}")
    except Exception as e:
        print(f"Erro ao ler PDF: {e}")
    return texto

#Função p/adicionar as letras/palavras ao arquivo PDF com formatação
def criar_pdf_texto(texto_lista, caminho_saida):
    c = canvas.Canvas(caminho_saida, pagesize=letter)
    textobject = c.beginText(100, 750)
    texto_para_falar = ""
    for item in texto_lista:
        textobject.textLine(item)
        texto_para_falar += item + " " 
    c.drawText(textobject)
    c.save()
    print(f"PDF '{caminho_saida}' atualizado com a lista de gestos.")
    return texto_para_falar, caminho_saida 

#Função p/obter a palavra "fechar" e fechar a webcam
def reconhecer_voz_fechar():
    global webcam_aberta
    r = sr.Recognizer()

    with sr.Microphone() as source:
        print("Diga 'fechar' para encerrar a webcam...")
        r.adjust_for_ambient_noise(source)

        while webcam_aberta:
            try:
                audio = r.listen(source, timeout=1)
                texto = r.recognize_google(audio, language='pt-BR')
                print(f"Você disse: {texto}")
                if "fechar" in texto.lower():
                    webcam_aberta = False
                    if video_capture and video_capture.isOpened():
                        video_capture.release()
                    if webcam_label:
                        webcam_label.destroy()
                    print("Webcam encerrada por comando de voz.")
                    break
            except sr.WaitTimeoutError:
                pass
            except sr.UnknownValueError:
                pass
            except sr.RequestError as e:
                print(f"Não foi possível acessar o serviço de reconhecimento de voz: {e}")
                break
            except Exception as e:
                print(f"Ocorreu um erro inesperado no reconhecimento de voz: {e}")
                break

#Função p/reproduzir em áudio o texto/letras
def falar_texto(texto):
    try:
        global engine
        engine.say(texto)
        engine.runAndWait()
    except Exception as e:
        print(f"Erro ao falar o texto: {e}")

def atualizar_frame_webcam():
    global webcam_aberta, video_capture, webcam_label, texto_reconhecido, engine, ultimo_tempo_falado

    if webcam_aberta and video_capture and video_capture.isOpened():
        success, frame = video_capture.read()
        if success:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = hands.process(frame_rgb)

            gesto_reconhecido = None
            similaridade_maxima = 0
            tempo_atual = time.time()

            if results.multi_hand_landmarks:
                for hand_landmarks in results.multi_hand_landmarks:
                    pontos_mao = np.array([[lm.x, lm.y] for lm in hand_landmarks.landmark])
                    min_coords = np.min(pontos_mao, axis=0)
                    max_coords = np.max(pontos_mao, axis=0)
                    if np.all(max_coords > min_coords):
                        pontos_normalizados = (pontos_mao - min_coords) / (max_coords - min_coords)

                        similaridade_video1 = calcular_similaridade_landmarks(pontos_normalizados, landmarks_video1)
                        similaridade_video2 = calcular_similaridade_landmarks(pontos_normalizados, landmarks_video2)
                        similaridade_video3 = calcular_similaridade_landmarks(pontos_normalizados, landmarks_video3)
                        similaridade_video4 = calcular_similaridade_landmarks(pontos_normalizados, landmarks_video4)
                        similaridade_video5 = calcular_similaridade_landmarks(pontos_normalizados, landmarks_video5)
                        similaridade_video6 = calcular_similaridade_landmarks(pontos_normalizados, landmarks_video6)
                        similaridade_video7 = calcular_similaridade_landmarks(pontos_normalizados, landmarks_video7)
                        similaridade_video8 = calcular_similaridade_landmarks(pontos_normalizados, landmarks_video8)
                        similaridade_video9 = calcular_similaridade_landmarks(pontos_normalizados, landmarks_video9)
                        similaridade_video10 = calcular_similaridade_landmarks(pontos_normalizados, landmarks_video10)
                        similaridade_video11 = calcular_similaridade_landmarks(pontos_normalizados, landmarks_video11)

                        if similaridade_video1 > MIN_SIMILARIDADE and similaridade_video1 > similaridade_maxima and (tempo_atual - ultimo_tempo_deteccao["oi"] > TEMPO_MINIMO_ENTRE_DETECOES):
                            similaridade_maxima = similaridade_video1
                            gesto_reconhecido = "oi"
                        if similaridade_video2 > MIN_SIMILARIDADE and similaridade_video2 > similaridade_maxima and (tempo_atual - ultimo_tempo_deteccao["tudo bem"] > TEMPO_MINIMO_ENTRE_DETECOES):
                            similaridade_maxima = similaridade_video2
                            gesto_reconhecido = "tudo bem"
                        if similaridade_video3 > MIN_SIMILARIDADE and similaridade_video3 > similaridade_maxima and (tempo_atual - ultimo_tempo_deteccao["eu sou"] > TEMPO_MINIMO_ENTRE_DETECOES):
                            similaridade_maxima = similaridade_video3
                            gesto_reconhecido = "eu sou"
                        if similaridade_video4 > MIN_SIMILARIDADE and similaridade_video4 > similaridade_maxima and (tempo_atual - ultimo_tempo_deteccao["Jessica Silva"] > TEMPO_MINIMO_ENTRE_DETECOES):
                            similaridade_maxima = similaridade_video4
                            gesto_reconhecido = "Jessica Silva"
                        if similaridade_video5 > MIN_SIMILARIDADE and similaridade_video5 > similaridade_maxima and (tempo_atual - ultimo_tempo_deteccao["aluna da escola do futuro EFG"] > TEMPO_MINIMO_ENTRE_DETECOES):
                            similaridade_maxima = similaridade_video5
                            gesto_reconhecido = "aluna da escola do futuro EFG"
                        if similaridade_video6 > MIN_SIMILARIDADE and similaridade_video6 > similaridade_maxima and (tempo_atual - ultimo_tempo_deteccao["do curso de ciencia de dados"] > TEMPO_MINIMO_ENTRE_DETECOES):
                            similaridade_maxima = similaridade_video6
                            gesto_reconhecido = "do curso de ciencia de dados"
                        if similaridade_video7 > MIN_SIMILARIDADE and similaridade_video7 > similaridade_maxima and (tempo_atual - ultimo_tempo_deteccao["esse projeto"] > TEMPO_MINIMO_ENTRE_DETECOES):
                            similaridade_maxima = similaridade_video7
                            gesto_reconhecido = "esse projeto"
                        if similaridade_video8 > MIN_SIMILARIDADE and similaridade_video8 > similaridade_maxima and (tempo_atual - ultimo_tempo_deteccao["tem como objetivo"] > TEMPO_MINIMO_ENTRE_DETECOES):
                            similaridade_maxima = similaridade_video8
                            gesto_reconhecido = "tem como objetivo"
                        if similaridade_video9 > MIN_SIMILARIDADE and similaridade_video9 > similaridade_maxima and (tempo_atual - ultimo_tempo_deteccao["a inclusao de todos"] > TEMPO_MINIMO_ENTRE_DETECOES):
                            similaridade_maxima = similaridade_video9
                            gesto_reconhecido = "a inclusao de todos"
                        if similaridade_video10 > MIN_SIMILARIDADE and similaridade_video10 > similaridade_maxima and (tempo_atual - ultimo_tempo_deteccao["que falam e necessitam de libras"] > TEMPO_MINIMO_ENTRE_DETECOES):
                            similaridade_maxima = similaridade_video10
                            gesto_reconhecido = "que falam e necessitam de libras"
                        if similaridade_video11 > MIN_SIMILARIDADE and similaridade_video11 > similaridade_maxima and (tempo_atual - ultimo_tempo_deteccao["de libras"] > TEMPO_MINIMO_ENTRE_DETECOES):
                            similaridade_maxima = similaridade_video11
                            gesto_reconhecido = "de libras"

                        mp_drawing.draw_landmarks(frame, hand_landmarks, solucao_reconhecimento_maos.HAND_CONNECTIONS)

            cv2.putText(frame, "sinal", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

            if gesto_reconhecido:
                cv2.putText(frame, f"Gesto: {gesto_reconhecido}", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)
                global texto_reconhecido
                texto_reconhecido += gesto_reconhecido 
                ultimo_tempo_deteccao[gesto_reconhecido] = tempo_atual

                #Reproduzir o áudio quase em tempo real
                if tempo_atual - ultimo_tempo_falado.get(gesto_reconhecido, 0) > TEMPO_MINIMO_FALA:
                    threading.Thread(target=falar_texto_async, args=(gesto_reconhecido,)).start()
                    ultimo_tempo_falado[gesto_reconhecido] = tempo_atual

                time.sleep(0.2) #Pequena pausa visual
            else:
                cv2.putText(frame, "", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

            img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            imgtk = ImageTk.PhotoImage(image=img)
            webcam_label.imgtk = imgtk
            webcam_label.config(image=imgtk)
        else:
            webcam_label.config(text="Erro ao capturar frame da webcam.")
    janela.after(10, atualizar_frame_webcam)

#Função p/falar o texto em uma thread separada
def falar_texto_async(texto):
    try:
        global engine  
        rate = engine.getProperty('rate')
        engine.say(texto)
        engine.runAndWait()
    except Exception as e:
        print(f"Erro ao falar o texto: {e}")

#Função p/manusear a webcam
def iniciar_webcam():
    global webcam_aberta, video_capture, webcam_label, hands, ultimo_tempo_deteccao, landmarks_video1, landmarks_video2, landmarks_video3, landmarks_video4, landmarks_video5, landmarks_video6, landmarks_video7, landmarks_video8, landmarks_video9, landmarks_video10, landmarks_video11, texto_reconhecido, ultimo_tempo_falado
    texto_reconhecido = "" 
    ultimo_tempo_falado = {} 

    if not webcam_aberta:
        caminho_video1 = "banco_videos/img1.png" #Caminho do video1
        caminho_video2 = "banco_videos/img2.png" #Caminho do video2
        caminho_video3 = "banco_videos/img3.png" #Caminho do video3
        caminho_video4 = "banco_videos/img4.png" #Caminho do video4
        caminho_video5 = "banco_videos/img5.png" #Caminho do video5
        caminho_video6 = "banco_videos/img6.png" #Caminho do video6
        caminho_video7 = "banco_videos/img7.png" #Caminho do video7
        caminho_video8 = "banco_videos/img8.png" #Caminho do video8
        caminho_video9 = "banco_videos/img9.png" #Caminho do video9
        caminho_video10 = "banco_videos/img10.png" #Caminho do video10
        caminho_video11 = "banco_videos/img11.png" #Caminho do video11

        landmarks_video1 = extrair_landmarks_video(caminho_video1)
        landmarks_video2 = extrair_landmarks_video(caminho_video2)
        landmarks_video3 = extrair_landmarks_video(caminho_video3)
        landmarks_video4 = extrair_landmarks_video(caminho_video4)
        landmarks_video5 = extrair_landmarks_video(caminho_video5)
        landmarks_video6 = extrair_landmarks_video(caminho_video6)
        landmarks_video7 = extrair_landmarks_video(caminho_video7)
        landmarks_video8 = extrair_landmarks_video(caminho_video8)
        landmarks_video9 = extrair_landmarks_video(caminho_video9)
        landmarks_video10 = extrair_landmarks_video(caminho_video10)
        landmarks_video11 = extrair_landmarks_video(caminho_video11)

        ultimo_tempo_deteccao = {"oi": 0, "tudo bem": 0, "eu sou": 0, "Jessica Silva": 0, "aluna da escola do futuro EFG":0, "do curso de ciencia de dados":0, "esse projeto":0, "tem como objetivo":0, "a inclusao de todos":0, "que falam e necessitam de libras":0, "de libras":0} #Pode modificar essas letras/palavras

        video_capture = cv2.VideoCapture(0)
        if not video_capture.isOpened():
            messagebox.showerror("Erro", "Não foi possível acessar a webcam.")
            return

        webcam_aberta = True
        bot_webcam.config(text="Desligar Webcam", command=desligar_webcam)

        if webcam_label is None:
            webcam_label = tk.Label(janela)
            webcam_label.place(relx=0.5, rely=0.25, anchor=tk.CENTER, width=640, height=480) #Localização na janela
        else:
            webcam_label.place(relx=0.5, rely=0.25, anchor=tk.CENTER, width=640, height=480)
            webcam_label.config(text="") #Limpa qualquer texto anterior

        global hands
        hands = solucao_reconhecimento_maos.Hands(
            max_num_hands=1,
            min_detection_confidence=DETECTION_CONFIDENCE,
            min_tracking_confidence=TRACKING_CONFIDENCE
        )
        atualizar_frame_webcam()

        #Eeconhecimento de voz em segundo plano
        voz_thread = threading.Thread(target=reconhecer_voz_fechar)
        voz_thread.daemon = True
        voz_thread.start()

#Função p/desligar a webcam
def desligar_webcam():
    global webcam_aberta, video_capture, webcam_label, hands
    if webcam_aberta:
        webcam_aberta = False
        bot_webcam.config(text="Ligar Webcam", command=iniciar_webcam)
        if video_capture and video_capture.isOpened():
            video_capture.release()
        if webcam_label:
            webcam_label.place_forget() #Para esconder a webcam
            webcam_label.config(text="")
        if hands:
            hands.close()
        print("Webcam desligada.")

#main (layout)
janela = tk.Tk()
janela.title("Conversão de texto p/voz/img")
janela.geometry('1280x720')

janela.grid_rowconfigure(0, weight=1)
janela.grid_columnconfigure(0, weight=1)
janela.grid_columnconfigure(1, weight=1)
janela.grid_columnconfigure(2, weight=1)

#Botões
bot_selecionar = tk.Button(janela, text="Selecionar PDF", command=selecionar)
bot_selecionar.place(relx=0.2, rely=0.7, anchor=tk.CENTER)

bot_ler = tk.Button(janela, text="Ler PDF", command=ler)
bot_ler.place(relx=0.4, rely=0.7, anchor=tk.CENTER)

bot_img = tk.Button(janela, text="Exibir Imagens", command=exibir_img)
bot_img.place(relx=0.6, rely=0.7, anchor=tk.CENTER)

bot_audio = tk.Button(janela, text="Converter Áudio", command=conv_audio_texto)
bot_audio.place(relx=0.8, rely=0.7, anchor=tk.CENTER)

bot_webcam = tk.Button(janela, text="Ligar Webcam", command=iniciar_webcam)
bot_webcam.place(relx=0.5, rely=0.8, anchor=tk.CENTER)

#Label para exibir a webcam
webcam_label = tk.Label(janela)
webcam_label.place(relx=0.5, rely=0.25, anchor=tk.CENTER, width=640, height=480)

#Inicializar variáveis globais para landmarks
landmarks_video1 = None
landmarks_video2 = None
landmarks_video3 = None
landmarks_video4 = None
landmarks_video5 = None
landmarks_video6 = None
landmarks_video7 = None
landmarks_video8 = None
landmarks_video9 = None
landmarks_video10 = None
landmarks_video11 = None
hands = None
ultimo_tempo_deteccao = {}
ultimo_tempo_falado = {}

janela.mainloop()

#Após fechar a janela principal, processar o PDF e falar
if __name__ == '__main__':
    nome_arquivo_letras = "letras_palavras_detectadas.pdf"
    if os.path.exists(nome_arquivo_letras):
        os.remove(nome_arquivo_letras) #Remover o PDF antigo

    if texto_reconhecido:
        lista_gestos = texto_reconhecido.strip().split('\n')
        texto_para_falar, _ = criar_pdf_texto(lista_gestos, nome_arquivo_letras)
        print(f"Gestos reconhecidos e salvos em '{nome_arquivo_letras}'.")
        falar_texto(texto_para_falar.strip()) #Fala o texto retornado pela função
    else:
        print("Nenhum gesto foi reconhecido.")