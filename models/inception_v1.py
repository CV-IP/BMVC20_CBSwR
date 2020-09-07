from collections import OrderedDict
import torch
import torch.nn as nn
import os
import hickle
from .util_layers import Normalize

# originate from
# https://github.com/vadimkantorov/metriclearningbench
class inception_v1_encoder(nn.Sequential):
    output_size = 1024
    input_side = 227
    rescale = 255.0
    rgb_mean = [122.7717, 115.9465, 102.9801]
    rgb_std = [1, 1, 1]

    def __init__(self):
        super(inception_v1_encoder, self).__init__(OrderedDict([
            ('conv1', nn.Sequential(OrderedDict([
                ('7x7_s2', nn.Conv2d(3, 64, (7, 7), (2, 2), (3, 3))),
                ('relu1', nn.ReLU(True)),
                ('pool1', nn.MaxPool2d((3, 3), (2, 2), ceil_mode=True)),
                ('lrn1', nn.CrossMapLRN2d(5, 0.0001, 0.75, 1))
            ]))),

            ('conv2', nn.Sequential(OrderedDict([
                ('3x3_reduce', nn.Conv2d(64, 64, (1, 1), (1, 1), (0, 0))),
                ('relu1', nn.ReLU(True)),
                ('3x3', nn.Conv2d(64, 192, (3, 3), (1, 1), (1, 1))),
                ('relu2', nn.ReLU(True)),
                ('lrn2', nn.CrossMapLRN2d(5, 0.0001, 0.75, 1)),
                ('pool2', nn.MaxPool2d((3, 3), (2, 2), ceil_mode=True))
            ]))),

            ('inception_3a', InceptionModule(192, 64, 96, 128, 16, 32, 32)),
            ('inception_3b', InceptionModule(256, 128, 128, 192, 32, 96, 64)),

            ('pool3', nn.MaxPool2d((3, 3), (2, 2), ceil_mode=True)),

            ('inception_4a', InceptionModule(480, 192, 96, 208, 16, 48, 64)),
            ('inception_4b', InceptionModule(512, 160, 112, 224, 24, 64, 64)),
            ('inception_4c', InceptionModule(512, 128, 128, 256, 24, 64, 64)),
            ('inception_4d', InceptionModule(512, 112, 144, 288, 32, 64, 64)),
            ('inception_4e', InceptionModule(528, 256, 160, 320, 32, 128, 128)),

            ('pool4', nn.MaxPool2d((3, 3), (2, 2), ceil_mode=True)),

            ('inception_5a', InceptionModule(832, 256, 160, 320, 32, 128, 128)),
            ('inception_5b', InceptionModule(832, 384, 192, 384, 48, 128, 128)),

            ('pool5', nn.AvgPool2d((7, 7), (1, 1), ceil_mode=True)),

            # ('drop5', nn.Dropout(0.4))
        ]))


# class inception_v1_decoder(nn.Sequential):
#     def __init__(self):
#         super(inception_v1_decoder, self).__init__(OrderedDict([
#             ('deconv1', nn.ConvTranspose2d(1024, 128, 5, 2, 2, 1)),
#             ('relu1', nn.ReLU(True)),
#             ('bn1', nn.BatchNorm2d(128)),
#             ('deconv2', nn.ConvTranspose2d(128, 64, 5, 2, 2, 1)),
#             ('relu2', nn.ReLU(True)),
#             ('bn2', nn.BatchNorm2d(64)),
#             ('deconv3', nn.ConvTranspose2d(64, 32, 5, 2, 2, 1)),
#             ('relu3', nn.ReLU(True)),
#             ('bn3', nn.BatchNorm2d(32)),
#             ('deconv4', nn.ConvTranspose2d(32, 3, 5, 2, 2, 1)),
#             ('tanh', nn.Tanh())
#         ]))


class inception_v1_decoder(nn.Sequential):
    def __init__(self):
        super(inception_v1_decoder, self).__init__(OrderedDict([
            # ('upsample7', nn.Upsample(scale_factor=7)),
            # ('deconv1', nn.ConvTranspose2d(1024, 1024, 7, 3, 1, 2)),
            ('inception_5b', InceptionModule(1024, 256, 160, 320, 32, 128, 128)),
            ('inception_5a', InceptionModule(832, 256, 160, 320, 32, 128, 128)),
            ('upsample14x14', nn.Upsample(scale_factor=2)),
            ('inception_4e', InceptionModule(832, 112, 144, 288, 32, 64, 64)),
            ('inception_4d', InceptionModule(528, 128, 128, 256, 24, 64, 64)),
            ('inception_4c', InceptionModule(512, 160, 112, 224, 24, 64, 64)),
            ('inception_4b', InceptionModule(512, 192, 96, 208, 16, 48, 64)),
            ('inception_4a', InceptionModule(512, 128, 128, 192, 32, 96, 64)),
            ('upsample28x28', nn.Upsample(scale_factor=2)),
            ('inception_3b', InceptionModule(480, 64, 96, 128, 16, 32, 32)),
            ('upsample28x28', nn.Upsample(scale_factor=2)),

            ('conv2', nn.Sequential(OrderedDict([
                ('3x3', nn.Conv2d(256, 192, (3, 3), (1, 1), (1, 1))),
                ('relu2', nn.ReLU(True)),
                ('bn2', nn.BatchNorm2d(192)),
                ('3x3_reduce', nn.Conv2d(192, 64, (1, 1), (1, 1), (0, 0))),
                ('relu1', nn.ReLU(True)),
                ('lrn2', nn.CrossMapLRN2d(5, 0.0001, 0.75, 1)),
            ]))),

            ('conv1', nn.Sequential(OrderedDict([
                ('upsample56x56', nn.Upsample(scale_factor=2)),
                ('deconv2', nn.ConvTranspose2d(64, 64, 7, 2, 3, 1)),
                ('relu', nn.ReLU(True)),
                ('bn', nn.BatchNorm2d(64)),
                ('deconv3', nn.ConvTranspose2d(64, 3, 7, 2, 3, 1)),
                ('tanh', nn.Tanh())
            ])))
        ]))


class InceptionModule(nn.Module):
    def __init__(self, inplane, outplane_a1x1, outplane_b3x3_reduce, outplane_b3x3, outplane_c5x5_reduce, outplane_c5x5,
                 outplane_pool_proj):
        super(InceptionModule, self).__init__()
        a = nn.Sequential(OrderedDict([
            ('1x1', nn.Conv2d(inplane, outplane_a1x1, (1, 1), (1, 1), (0, 0))),
            ('1x1_relu', nn.ReLU(True))
        ]))

        b = nn.Sequential(OrderedDict([
            ('3x3_reduce', nn.Conv2d(inplane, outplane_b3x3_reduce, (1, 1), (1, 1), (0, 0))),
            ('3x3_relu1', nn.ReLU(True)),
            ('3x3', nn.Conv2d(outplane_b3x3_reduce, outplane_b3x3, (3, 3), (1, 1), (1, 1))),
            ('3x3_relu2', nn.ReLU(True))
        ]))

        c = nn.Sequential(OrderedDict([
            ('5x5_reduce', nn.Conv2d(inplane, outplane_c5x5_reduce, (1, 1), (1, 1), (0, 0))),
            ('5x5_relu1', nn.ReLU(True)),
            ('5x5', nn.Conv2d(outplane_c5x5_reduce, outplane_c5x5, (5, 5), (1, 1), (2, 2))),
            ('5x5_relu2', nn.ReLU(True))
        ]))

        d = nn.Sequential(OrderedDict([
            ('pool_pool', nn.MaxPool2d((3, 3), (1, 1), (1, 1))),
            ('pool_proj', nn.Conv2d(inplane, outplane_pool_proj, (1, 1), (1, 1), (0, 0))),
            ('pool_relu', nn.ReLU(True))
        ]))

        for container in [a, b, c, d]:
            for name, module in container.named_children():
                self.add_module(name, module)

        self.branches = [a, b, c, d]

    def forward(self, input):
        return torch.cat([branch(input) for branch in self.branches], 1)


class Model(nn.Module):
    def __init__(self, base_model, low_dim=128):
        super(Model, self).__init__()
        self.base_model = base_model
        self.embedder = nn.Linear(base_model.output_size, low_dim)
        self.l2norm = Normalize(2)

        # base_model = inception_v1_googlenet()

    def forward(self, input):
        pool5 = self.base_model(input).view(len(input), -1)
        embed = self.embedder(pool5)
        embed = self.l2norm(embed)
        if self.training:
            return embed
        else:
            return embed, self.l2norm(pool5)


def inception_v1_ml(pretrained=False, low_dim=128):
    base_model = inception_v1_encoder()
    base_model_weights_path = 'models/googlenet.h5'
    if os.path.exists(base_model_weights_path):
        base_model.load_state_dict(
            {k: torch.from_numpy(v).cuda() for k, v in hickle.load(base_model_weights_path).items()})
    # base_model = models.googlenet(pretrained=True)
    # base_model = torch.nn.Sequential(*list(base_model.children())[:-2])
    net = Model(base_model, low_dim)
    return net
