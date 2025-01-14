from model import *
from data import *

import os

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

from _collections import defaultdict
import numpy as np
import random
import argparse

class ValidDataset(Dataset):

    def __init__(self, file_name, test_name):
        self.entity2id, self.id2entity = load_dict('../' + file_name + '/entity2id.txt')
        self.rel2id, self.id2rel = load_dict('../' + file_name + '/relation2id.txt')

        self.entity2data_list, self.rel2entity_list = load_data('../' + file_name + '/train.txt', self.entity2id, self.rel2id)

        self.entity_len = len(self.entity2id)
        self.rel_len = len(self.rel2id)

        self.id2e1_test, self.id2e2_test, self.id2rel_test, self.id2flag_test = load_test_data('../' + file_name + '/' + test_name, self.entity2id, self.rel2id)
        self.len = len(self.id2e1_test)

    def get_data(self, h, r, t):
        r_list = []
        e_list = []

        data = self.entity2data_list[h]
        # if (r, t) in data:
        #     data.remove((r, t))
        data.append((self.rel_len, h))
        
        for (rel, entity) in data:
            r_list.append(rel * self.rel_len + r)
            e_list.append(entity)

        DATA_len = 50
        data_len = len(r_list)
        if data_len > DATA_len:
            ids = random.sample(range(0, data_len), DATA_len)
            r_data = [r_list[idx] for idx in ids]
            e_data = [e_list[idx] for idx in ids]
        else:
            r_data = r_list
            e_data = e_list

        data_len = len(r_data)
        data_r = torch.from_numpy(np.array(r_data)).int()
        data_r_temp = torch.ones((DATA_len - data_len), dtype=torch.int) * (self.rel_len * (self.rel_len + 1))
        data_r = torch.cat((data_r, data_r_temp), 0)
        
        data_e = torch.from_numpy(np.array(e_data)).int()
        data_e_temp = torch.ones((DATA_len - data_len), dtype=torch.int) * self.entity_len
        data_e = torch.cat((data_e, data_e_temp), 0)

        return data_r, data_e

    def __getitem__(self, index):
        e1 = self.id2e1_test[index]
        e2 = self.id2e2_test[index]
        rel = self.id2rel_test[index]
        flag = self.id2flag_test[index]

        data_r, data_e = self.get_data(e1, rel, e2)

        flag = int(flag)

        return data_r, data_e, rel, e2, flag

    def __len__(self):
        return self.len

def valid(file_name, net_path, test_name, start, end):
    valid_dataset = ValidDataset(file_name, test_name)
    valid_dataloader = DataLoader(valid_dataset, shuffle=False, num_workers=1, batch_size=1000)

    # net = torch.load(net_path)
    net = Network(args.dim, valid_dataset.entity_len, valid_dataset.rel_len)
    net.load_state_dict(torch.load(net_path))
    net.eval()

    

    pdist = nn.PairwiseDistance(p=2)

    out_dict = defaultdict(list)

    for i, data in enumerate(valid_dataloader, 0):
        data_r, data_e, rel, t, flag = data

        vh = net.get_vh(data_r, data_e)
        vr = net.get_vr(rel)
        vt = net.get_vt(t)

        dist = pdist(vh + vr, vt)

        dist = dist.data.numpy()
        rel = rel.numpy()
        flag = flag.numpy()

        data_len = t.size(0)
        for idx in range(data_len): 
            out_dict[(rel[idx], flag[idx])].append(dist[idx])

    right_dict = defaultdict(list)
    count_dict =defaultdict(int)
    for r in valid_dataset.id2rel:
        pos_list = out_dict[(r, 1)]
        neg_list = out_dict[(r, -1)]
        rel_name = valid_dataset.id2rel[r]

        count = len(pos_list) + len(neg_list)
        if count == 0:
            break
        else:
            count_dict[rel_name] = count

        for margin in range(start, end):
            pos_count = 0
            neg_count = 0
            for pos in pos_list:
                if pos < margin:
                    pos_count += 1
            for neg in neg_list:
                if neg >= margin:
                    neg_count += 1
            right = pos_count + neg_count

            right_dict[rel_name].append(right)

    return list(valid_dataset.rel2id.keys()), right_dict, count_dict

def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-dim', type=int, default=50, help='entity and relation sharing embedding dimension')
    parser.add_argument('-margin_pos', type=int, default=1, help='margin of positive triplets')
    parser.add_argument('-margin_neg', type=int, default=100, help='margin of negative triplets')
    parser.add_argument('-rate', type=float, default=0.0001, help='learning rate')
    parser.add_argument('-batch', type=int, default=1000, help='batch size')
    parser.add_argument('-epoch', type=int, default=300, help='number of training epoch')
    parser.add_argument('-method', type=str, default='bern', help='stratege of constructing negative triplets')
    parser.add_argument('-data', type=str, default='FB13', help='dataset of the model')
    parser.add_argument('-start', type=int, default=0, help='beginning of the threshold')
    parser.add_argument('-end', type=int, default=110, help='end of the threshold')
    args = parser.parse_args()

    return args

if __name__ == '__main__':
    args = get_args()

    file_name = args.data
    net_name = str(args.dim) + '-' + str(args.margin_pos) + '-' + str(args.margin_neg) + '(' + str(args.rate) + '-' + str(args.batch) + ')-' + args.method
    epoch = args.epoch
    start = args.start
    end = args.end

    test_name = 'valid.txt'
    net_path = 'out/' + file_name + '/' + net_name + '/net-' + str(epoch) + '.pt'
    out_path = 'out/' + file_name + '/' + net_name + '/valid/'

    if not os.path.exists(out_path):
        os.makedirs(out_path)
    
    rel_list, right_dict, count_dict = valid(file_name, net_path, test_name, start, end)
    right_sum = 0
    count = 0

    line = '%d\t%d' % (start, end)
    write(out_path + str(epoch) + '.txt', line)
    margin_list = np.arange(start, end)

    for rel in rel_list:
        if rel not in right_dict.keys():
            continue
        rights = right_dict[rel]
        index = np.argmax(rights)
        margin = margin_list[index]

        line = '%s\t%d' % (rel, margin)
        write(out_path + 'margin-' + str(epoch) + '.txt', line)
        right_sum += rights[index]
        count += count_dict[rel]

        line = rel
        for right in rights:
            line += '\t%.4f' % (right / count_dict[rel])
        write(out_path + str(epoch) + '.txt', line)

    line = '%d\t %.4f' % (epoch, right_sum / count)
    print(line)
    write(out_path + 'valid.txt', line)
    
