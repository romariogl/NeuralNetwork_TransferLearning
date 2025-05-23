import tensorflow as tf
from tensorflow import keras
import numpy as np
from tensorflow.keras.datasets import cifar10
from tensorflow.keras.preprocessing.image import ImageDataGenerator
from tensorflow.keras.layers import (
    BatchNormalization, Conv2D, Dense, Input, add, Activation, 
    GlobalAveragePooling2D
)
from tensorflow.keras.callbacks import LearningRateScheduler, TensorBoard, ModelCheckpoint
from tensorflow.keras.models import Model, load_model
from tensorflow.keras import optimizers, regularizers
import os

from networks.train_plot import PlotLearning

# Code taken from https://github.com/BIGBALLON/cifar-10-cnn
class ResNet:
    def __init__(self, epochs=200, batch_size=128, load_weights=True, num_classes=10, transfer_learning=False):
        self.name = 'resnet'
        self.model_filename = 'FeatureExtractor/networks/pretrained_weights/resnet.h5'
        
        self.stack_n = 5    
        self.num_classes = num_classes
        self.img_rows, self.img_cols = 32, 32
        self.img_channels = 3
        self.batch_size = batch_size
        self.epochs = epochs
        self.iterations = 50000 // self.batch_size
        self.weight_decay = 0.0001
        self.log_filepath = r'FeatureExtractor/networks/pretrained_weights/resnet/'
        self.transfer_learning = transfer_learning

        # Cria diretórios se não existirem
        os.makedirs('FeatureExtractor/networks/pretrained_weights', exist_ok=True)
        os.makedirs(self.log_filepath, exist_ok=True)

        # Inicializa o modelo
        img_input = Input(shape=(self.img_rows, self.img_cols, self.img_channels))
        output = self.residual_network(img_input, self.num_classes, self.stack_n)
        self._model = Model(img_input, output)

        if load_weights:
            try:
                # Tenta carregar apenas os pesos
                self._model.load_weights(self.model_filename)
                print('Successfully loaded weights for', self.name)
                
                if transfer_learning:
                    # Congela todas as camadas exceto a última
                    for layer in self._model.layers[:-1]:
                        layer.trainable = False
                    print('Camadas congeladas para transfer learning')
                    
                    # Recompila o modelo com as camadas congeladas
                    sgd = optimizers.SGD(learning_rate=0.01, momentum=0.9, nesterov=True)
                    self._model.compile(loss='categorical_crossentropy', optimizer=sgd, metrics=['accuracy'])
            except (ImportError, ValueError, OSError):
                print('Failed to load weights for', self.name)
                print('Training new model...')
                self.train()
    
    def count_params(self):
        return self._model.count_params()

    def color_preprocessing(self, x_train, x_test):
        x_train = x_train.astype('float32')
        x_test = x_test.astype('float32')
        # Normalização genérica para o intervalo [0, 1]
        x_train = x_train / 255.0
        x_test = x_test / 255.0
        return x_train, x_test

    def scheduler(self, epoch):
        if epoch < 80:
            return 0.1
        if epoch < 150:
            return 0.01
        return 0.001

    def residual_network(self, img_input,classes_num=10,stack_n=5):
        def residual_block(intput,out_channel,increase=False):
            if increase:
                stride = (2,2)
            else:
                stride = (1,1)

            pre_bn   = BatchNormalization()(intput)
            pre_relu = Activation('relu')(pre_bn)

            conv_1 = Conv2D(out_channel,kernel_size=(3,3),strides=stride,padding='same',
                            kernel_initializer="he_normal",
                            kernel_regularizer=regularizers.l2(self.weight_decay))(pre_relu)
            bn_1   = BatchNormalization()(conv_1)
            relu1  = Activation('relu')(bn_1)
            conv_2 = Conv2D(out_channel,kernel_size=(3,3),strides=(1,1),padding='same',
                            kernel_initializer="he_normal",
                            kernel_regularizer=regularizers.l2(self.weight_decay))(relu1)
            if increase:
                projection = Conv2D(out_channel,
                                    kernel_size=(1,1),
                                    strides=(2,2),
                                    padding='same',
                                    kernel_initializer="he_normal",
                                    kernel_regularizer=regularizers.l2(self.weight_decay))(intput)
                block = add([conv_2, projection])
            else:
                block = add([intput,conv_2])
            return block

        # build model
        # total layers = stack_n * 3 * 2 + 2
        # stack_n = 5 by default, total layers = 32
        # input: 32x32x3 output: 32x32x16
        x = Conv2D(filters=16,kernel_size=(3,3),strides=(1,1),padding='same',
                kernel_initializer="he_normal",
                kernel_regularizer=regularizers.l2(self.weight_decay))(img_input)

        # input: 32x32x16 output: 32x32x16
        for _ in range(stack_n):
            x = residual_block(x,16,False)

        # input: 32x32x16 output: 16x16x32
        x = residual_block(x,32,True)
        for _ in range(1,stack_n):
            x = residual_block(x,32,False)
        
        # input: 16x16x32 output: 8x8x64
        x = residual_block(x,64,True)
        for _ in range(1,stack_n):
            x = residual_block(x,64,False)

        x = BatchNormalization()(x)
        x = Activation('relu')(x)
        x = GlobalAveragePooling2D()(x)

        # input: 64 output: 10
        x = Dense(classes_num,activation='softmax',
                kernel_initializer="he_normal",
                kernel_regularizer=regularizers.l2(self.weight_decay))(x)
        return x

    def train(self, x_train=None, y_train=None, x_test=None, y_test=None):
        if x_train is None or y_train is None:
            # Se não fornecer dados, usa CIFAR-10
            (x_train, y_train), (x_test, y_test) = cifar10.load_data()
            y_train = keras.utils.to_categorical(y_train, self.num_classes)
            y_test = keras.utils.to_categorical(y_test, self.num_classes)
        else:
            # Converte os labels para one-hot encoding
            y_train = keras.utils.to_categorical(y_train, self.num_classes)
            y_test = keras.utils.to_categorical(y_test, self.num_classes)
        
        # color preprocessing
        x_train, x_test = self.color_preprocessing(x_train, x_test)

        # build network
        img_input = Input(shape=(self.img_rows, self.img_cols, self.img_channels))
        output = self.residual_network(img_input, self.num_classes, self.stack_n)
        resnet = Model(img_input, output)
        resnet.summary()

        # set optimizer
        sgd = optimizers.SGD(learning_rate=0.1, momentum=0.9, nesterov=True)
        resnet.compile(loss='categorical_crossentropy', optimizer=sgd, metrics=['accuracy'])

        # set callback
        tb_cb = TensorBoard(log_dir=self.log_filepath, histogram_freq=0)
        change_lr = LearningRateScheduler(self.scheduler)
        checkpoint = ModelCheckpoint(self.model_filename, 
                monitor='val_loss', verbose=0, save_best_only=True, mode='auto')
        plot_callback = PlotLearning()
        cbks = [change_lr, tb_cb, checkpoint, plot_callback]

        # set data augmentation
        print('Using real-time data augmentation.')
        datagen = ImageDataGenerator(
            horizontal_flip=True,
            width_shift_range=0.125,
            height_shift_range=0.125,
            fill_mode='constant',
            cval=0.
        )

        datagen.fit(x_train)

        # start training
        resnet.fit(
            datagen.flow(x_train, y_train, batch_size=self.batch_size),
            steps_per_epoch=self.iterations,
            epochs=self.epochs,
            callbacks=cbks,
            validation_data=(x_test, y_test)
        )
        resnet.save(self.model_filename)

        self._model = resnet
        self.param_count = self._model.count_params()

    def color_process(self, imgs):
        if imgs.ndim < 4:
            imgs = np.array([imgs])
        imgs = imgs.astype('float32')
        # Normalização genérica para o intervalo [0, 1]
        imgs = imgs / 255.0
        return imgs

    def predict(self, img):
        processed = self.color_process(img)
        return self._model.predict(processed, batch_size=self.batch_size)
    
    def predict_one(self, img):
        return self.predict(img)[0]

    def accuracy(self):
        (x_train, y_train), (x_test, y_test) = cifar10.load_data()
        y_train = keras.utils.to_categorical(y_train, self.num_classes)
        y_test = keras.utils.to_categorical(y_test, self.num_classes)
        
        # color preprocessing
        x_train, x_test = self.color_preprocessing(x_train, x_test)

        return self._model.evaluate(x_test, y_test, verbose=0)[1]