import librosa
import numpy as np
import soundfile as sf
print("Librosa imported")
y = np.zeros(22050)
S = np.abs(librosa.stft(y))**2
print("stft works")
print(librosa.feature.spectral_centroid(S=S, sr=22050).shape)
print("centroid works")
print(librosa.feature.chroma_stft(S=S, sr=22050).shape)
print("chroma works")
print(librosa.feature.mfcc(S=librosa.power_to_db(S), sr=22050).shape)
print("mfcc works")
