#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by sunder on 2017/8/21
import collections
import json
import logging
import sys
import unicodedata

import nltk
import numpy as np
np.random.seed(1666)

logger = logging.getLogger('mylogger')

InputData = collections.namedtuple('InputData', ['input_sentence_length',
                                                 'sentence_fw',
                                                 'sentence_bw',
                                                 'sentence_pos_fw',
                                                 'sentence_pos_bw',
                                                 'standard_outputs',
                                                 'input_sentence_append_eos',
                                                 'relations_append_eos',
                                                 'all_triples'])

TorchData = collections.namedtuple('InputData', ['sentence','triplets'])

class Data:
    def __init__(self, data, batch_size, config):

        standard_outputs, sentence_length, sentence_fw, sentence_bw, sentence_pos_fw, sentence_pos_bw, input_sentence_append_eos, relations_append_eos, all_triples_id = data
        self.standard_outputs = np.asanyarray(standard_outputs)
        self.all_triples_id = np.asanyarray(all_triples_id)  # gold triples without padding
        self.all_sentence = None

        self.sentence_length = np.asanyarray(sentence_length)
        self.sentence_fw = np.asanyarray(sentence_fw)
        self.sentence_bw = np.asanyarray(sentence_bw)
        self.sentence_pos_fw = np.asanyarray(sentence_pos_fw)
        self.sentence_pos_bw = np.asanyarray(sentence_pos_bw)
        self.input_sentence_append_eos = np.asanyarray(input_sentence_append_eos)
        self.relations_append_eos = np.asanyarray(relations_append_eos)
        self.instance_number = len(self.sentence_length)
        self.batch_size = batch_size
        self.batch_index = 0
        self.batch_number = int(self.instance_number / self.batch_size)
        self.config = config

    def next_batch(self, is_random=True):
        if is_random:
            indexes = self.next_random_indexes()
        else:
            indexes = self.next_sequence_indexes()

        all_triples = self.all_triples_id[indexes]
        standard_outputs = self.standard_outputs[indexes]
        input_sentence_length = self.sentence_length[indexes]
        sentence_fw = self.sentence_fw[indexes]
        sentence_bw = self.sentence_bw[indexes]
        sentence_pos_fw = self.sentence_pos_fw[indexes]
        sentence_pos_bw = self.sentence_pos_bw[indexes]
        input_sentence_append_eos = self.input_sentence_append_eos[indexes]
        relations_append_eos = self.relations_append_eos[indexes]

        sort_index = np.argsort(-input_sentence_length)

        batch_data = InputData(input_sentence_length=input_sentence_length[sort_index],
                               sentence_fw=sentence_fw[sort_index],
                               sentence_bw=sentence_bw[sort_index],
                               sentence_pos_fw=sentence_pos_fw[sort_index],
                               sentence_pos_bw=sentence_pos_bw[sort_index],
                               standard_outputs=standard_outputs[sort_index],
                               input_sentence_append_eos=input_sentence_append_eos[sort_index],
                               relations_append_eos=relations_append_eos[sort_index],
                               all_triples=all_triples[sort_index])
        # batch_data =TorchData(sentence=self.all_sentence[indexes], triplets=all_triples)
        # batch_data = TorchData(sentence=self.sentence_fw[indexes], triplets=standard_outputs)
        # batch_data = self.sentence_fw[indexes]
        return batch_data

    #   select data in sequence, mainly for test
    def next_sequence_indexes(self):
        if self.batch_index < self.batch_number:
            indexes = np.asanyarray(range(self.batch_size * self.batch_index, (self.batch_index + 1) * self.batch_size))
            self.batch_index += 1
            return indexes
        else:
            return None

    def reset(self):
        self.batch_index = 0

    # randomly select a batch of data, only for train
    def next_random_indexes(self):
        return np.random.choice(range(self.instance_number), self.batch_size)


def inverse(sent_index):
    inversed = []
    for sent in sent_index:
        sent = list(sent)
        sent.reverse()
        inversed.append(sent)
    return inversed


def padding_sentence(sent_index, config):
    return [padding_a_sentence(sent, config.max_sentence_length) for sent in sent_index]

def padding_a_sentence(sent, max_length):
    sent = list(sent)
    if len(sent) >= max_length:
        return sent[0: max_length]
    for i in range(max_length - len(sent)):
        sent.append(0)
    return sent
def padding_triples(all_triples_id, config):
    all_triples_id = [padding_a_triples(triples, config) for triples in all_triples_id]
    return all_triples_id


def padding_a_triples(triples, config):
    """
    Pad triples to given length
    If the given triples is over length, then, randomly select some of it's triples
    :param triples:
    :return: padded triples
    """
    triple_list = triples[:]
    max_length = config.decoder_output_max_length
    triples = [[triple_list[3 * i], triple_list[3 * i + 1], triple_list[3 * i + 2]] for i in
               range(len(triple_list) // 3)]
    np.random.shuffle(triples)
    padded = []
    for t in triples:
        padded.extend(t)

    if len(triple_list) >= max_length:
        padded = padded[: max_length]
    else:
        pad_triple = list(config.NA_TRIPLE)
        for _ in range((max_length - len(triple_list)) // 3):
            padded.extend(pad_triple)
    assert len(padded) == max_length
    return padded




def append_eos2sentence(sent_index, config):
    eos_idx = config.words_number
    appended = []
    for sent in sent_index:
        sent = list(sent)
        sent.append(eos_idx)
        appended.append(sent)
    return appended




def append_eos2relations(sent_number, config):
    relations_with_eos = range(config.words_number, config.words_number + config.relation_number + 1)
    return [relations_with_eos] * sent_number


def change2relation_first(triples):
    """
    original triple is (entity1, entity2, relation), now, change it as (relation, entity1, entity2)
    :param triples:
    :return: triples with relation first

    >>> change2relation_first([[1, 2, 23, 32, 19, 8],[0,28, 3_实体识别]])
    [[23, 1, 2, 8, 32, 19], [3_实体识别, 0, 28]]
    """
    triple_count = 0
    new_triples = []
    for t in triples:
        new = []
        for i in range(len(t) // 3):
            new_t = [t[3 * i + 2], t[3 * i], t[3 * i + 1]]
            new.extend(new_t)
        new_triples.append(new)
        triple_count += len(t) // 3
    logger.info('Gold triple number %d' % triple_count)
    return new_triples


def is_normal_triple(triples, is_relation_first=False):
    """
    normal triples means triples are not over lap in entity.
    example [e1,e2,r1, e3,e4,r2]
    :param triples
    :param is_relation_first
    :return:

    >>> is_normal_triple([1,2,3_实体识别, 4_实体识别_1_3的O,5,0])
    True
    >>> is_normal_triple([1,2,3_实体识别, 4_实体识别_1_3的O,5,3_实体识别])
    True
    >>> is_normal_triple([1,2,3_实体识别, 2,5,0])
    False
    >>> is_normal_triple([1,2,3_实体识别, 1,2,0])
    False
    >>> is_normal_triple([1,2,3_实体识别, 4_实体识别_1_3的O,5,0], is_relation_first=True)
    True
    >>> is_normal_triple([1,2,3_实体识别, 4_实体识别_1_3的O,5,3_实体识别], is_relation_first=True)
    False
    >>> is_normal_triple([1,2,3_实体识别, 2,5,0], is_relation_first=True)
    True
    >>> is_normal_triple([1,2,3_实体识别, 1,2,0], is_relation_first=True)
    False
    """
    entities = set()
    for i, e in enumerate(triples):
        key = 0 if is_relation_first else 2
        if i % 3 != key:
            entities.add(e)
    return len(entities) == 2 * len(triples) // 3


def is_multi_label(triples, is_relation_first=False):
    """
    :param triples:
    :param is_relation_first:
    :return:
    >>> is_multi_label([1,2,3_实体识别, 4_实体识别_1_3的O,5,0])
    False
    >>> is_multi_label([1,2,3_实体识别, 4_实体识别_1_3的O,5,3_实体识别])
    False
    >>> is_multi_label([1,2,3_实体识别, 2,5,0])
    False
    >>> is_multi_label([1,2,3_实体识别, 1,2,0])
    True
    >>> is_multi_label([1,2,3_实体识别, 4_实体识别_1_3的O,5,0], is_relation_first=True)
    False
    >>> is_multi_label([1,2,3_实体识别, 4_实体识别_1_3的O,5,3_实体识别], is_relation_first=True)
    False
    >>> is_multi_label([1,5,0, 2,5,0], is_relation_first=True)
    True
    >>> is_multi_label([1,2,3_实体识别, 1,2,0], is_relation_first=True)
    False
    """
    if is_normal_triple(triples, is_relation_first):
        return False
    if is_relation_first:
        entity_pair = [tuple(triples[3 * i + 1: 3 * i + 3]) for i in range(len(triples) // 3)]
    else:
        entity_pair = [tuple(triples[3 * i: 3 * i + 2]) for i in range(len(triples) // 3)]
    # if is multi label, then, at least one entity pair appeared more than once
    return len(entity_pair) != len(set(entity_pair))


def is_over_lapping(triples, is_relation_first=False):
    """
    :param triples:
    :param is_relation_first:
    :return:
    >>> is_over_lapping([1,2,3_实体识别, 4_实体识别_1_3的O,5,0])
    False
    >>> is_over_lapping([1,2,3_实体识别, 4_实体识别_1_3的O,5,3_实体识别])
    False
    >>> is_over_lapping([1,2,3_实体识别, 2,5,0])
    True
    >>> is_over_lapping([1,2,3_实体识别, 1,2,0])
    False
    >>> is_over_lapping([1,2,3_实体识别, 4_实体识别_1_3的O,5,0], is_relation_first=True)
    False
    >>> is_over_lapping([1,2,3_实体识别, 4_实体识别_1_3的O,5,3_实体识别], is_relation_first=True)
    True
    >>> is_over_lapping([1,5,0, 2,5,0], is_relation_first=True)
    False
    >>> is_over_lapping([1,2,3_实体识别, 1,2,0], is_relation_first=True)
    True
    """
    if is_normal_triple(triples, is_relation_first):
        return False
    if is_relation_first:
        entity_pair = [tuple(triples[3 * i + 1: 3 * i + 3]) for i in range(len(triples) // 3)]
    else:
        entity_pair = [tuple(triples[3 * i: 3 * i + 2]) for i in range(len(triples) // 3)]
    # remove the same entity_pair, then, if one entity appear more than once, it's overlapping
    entity_pair = set(entity_pair)
    entities = []
    for pair in entity_pair:
        entities.extend(pair)
    entities = set(entities)
    return len(entities) != 2 * len(entity_pair)


class Prepare:
    def __init__(self, config):
        self.config = config

    def load_words(self):
        return json.load(open(self.config.words2id_filename, 'r'))

    def load_relations(self):
        return json.load(open(self.config.relations2id_filename, 'r'))

    @staticmethod
    def remove_tone(s):
        s = unicodedata.normalize('NFD', s)
        cmb_chrs = dict.fromkeys(c for c in range(sys.maxunicode) if unicodedata.combining(unichr(c)))
        return s.translate(cmb_chrs)

    def load_data(self, name):
        if name.lower() == 'train':
            filename = self.config.train_filename
        elif name.lower() == 'test':
            filename = self.config.test_filename
        elif name.lower() == 'valid':
            filename = self.config.valid_filename
        else:
            print('name must be "train" or "test", but is %s' % name)
            raise ValueError
        print('loading %s' % filename)
        data = json.load(open(filename, 'r'))
        print('data size %d' % (len(data[0])))
        return data


class NYTPrepare(Prepare):
    @staticmethod
    def read_json(filename):
        data = []
        with open(filename, 'r') as f:
            for line in f:
                a_data = json.loads(line)
                data.append(a_data)
        return data

    #   flag is used to determine if save a sentence if it has no triples
    def turn2id(self, data, words2id, relations2id, flag=False):
        all_sent_id = []
        all_triples_id = []
        all_sent_length = []
        triples_number = []
        accept_count = 0
        for i, a_data in enumerate(data):
            is_save = True
            sent_text = a_data['sentText']
            sent_id = []
            for w in nltk.word_tokenize(sent_text):
                try:
                    w_id = words2id[w]
                    sent_id.append(w_id)
                except:
                    is_save = False
                    print('[%s] is not in words2id' % w)
            triples = a_data['relationMentions']
            triples_id = set()
            for triple in triples:
                # m1 = '_'.join(nltk.word_tokenize(triple['em1Text']))
                # m2 = '_'.join(nltk.word_tokenize(triple['em2Text']))
                m1 = nltk.word_tokenize(triple['em1Text'])[-1]
                m2 = nltk.word_tokenize(triple['em2Text'])[-1]
                label = triple['label']
                if label != 'None':
                    if m2 not in words2id:
                        m2 = self.remove_tone(m2)
                    if m1 not in words2id:
                        m1 = self.remove_tone(m1)
                    try:
                        t_id = (sent_id.index(words2id[m1]), sent_id.index(words2id[m2]),
                                relations2id[label])
                        triples_id.add(t_id)
                    except:
                        is_save = False
                        print('[%s] or [%s] is not in words2id, relation is (%s)' % (m1, m2, label))
            if len(sent_id) <= self.config.max_sentence_length and is_save:
                if flag and len(triples_id) == 0:  # this sentence has no triple and assign a  to it
                    triples_id.add(self.config.NA_TRIPLE)
                    assert len(triples_id) == 1
                if len(triples_id) > 0:
                    accept_count += 1
                    triples = []
                    for t in triples_id:
                        triples.extend(list(t))
                    triples_number.append(len(triples_id))
                    all_triples_id.append(triples)
                    all_sent_id.append(sent_id)
                    all_sent_length.append(len(sent_id))
            if (i + 1) * 1.0 % 1000 == 0:
                print('finish %f, %d/%d, accept %d' % ((i + 1.0) // len(data), (i + 1), len(data), accept_count))

        assert len(all_triples_id) == len(all_sent_id)
        assert len(all_sent_length) == len(all_sent_id)
        print('instance number %d/%d' % (len(all_sent_id), len(data)))
        print('triples number max %d, min %d, ave %f' % (
        max(triples_number), min(triples_number), np.mean(triples_number)))

        return [all_sent_length, all_sent_id, all_triples_id]

    def prepare(self):
        train_data = self.read_json(self.config.raw_train_filename)
        test_data = self.read_json(self.config.raw_test_filename)
        valid_data = self.read_json(self.config.raw_valid_filename)

        words2id = self.load_words()
        relations2id = self.load_relations()

        print('processing train data')
        train_data = self.turn2id(train_data, words2id, relations2id)
        json.dump(train_data, open(self.config.train_filename, 'w'))

        print('processing test data')
        test_data = self.turn2id(test_data, words2id, relations2id)
        json.dump(test_data, open(self.config.test_filename, 'w'))

        print('processing valid data')
        valid_data = self.turn2id(valid_data, words2id, relations2id)
        json.dump(valid_data, open(self.config.valid_filename, 'w'))
        print('success')

    #   Above functions are processing raw data
    #   Below functions are prepare the feeding data
    def process(self, data):
        all_sent_length, all_sent_id, all_triples_id = data
        all_triples_id = change2relation_first(all_triples_id)
        standard_outputs = padding_triples(all_triples_id, self.config)
        sentence_length = all_sent_length
        sentence_fw = padding_sentence(all_sent_id, self.config)
        sentence_bw = padding_sentence(inverse(all_sent_id), self.config)
        input_sentence_append_eos = append_eos2sentence(sentence_fw, self.config)
        relations_append_eos = append_eos2relations(len(sentence_fw), self.config)
        return [standard_outputs, sentence_length, sentence_fw, sentence_bw, [None] * len(sentence_fw),
                [None] * len(sentence_fw), input_sentence_append_eos, relations_append_eos, all_triples_id]

    def analyse_data(self, name):
        [_, _, all_triples_id] = self.load_data(name)
        normal_count = 0
        multi_label_count = 0
        over_lapping_count = 0
        for sent_triples in all_triples_id:
            normal_count += 1 if is_normal_triple(sent_triples) else 0
            multi_label_count += 1 if is_multi_label(sent_triples) else 0
            over_lapping_count += 1 if is_over_lapping(sent_triples) else 0
            # if is_normal_triple(sent_triples):
            #     print sent_triples
        print('Normal Count %d, Multi label Count %d, Overlapping Count %d' % (
        normal_count, multi_label_count, over_lapping_count))
        print('Normal Rate %f, Multi label Rate %f, Overlapping Rate %f' % \
              (normal_count * 1.0 / len(all_triples_id), multi_label_count * 1.0 / len(all_triples_id),
               over_lapping_count * 1.0 / len(all_triples_id)))

        triples_size_1, triples_size_2, triples_size_3, triples_size_4, triples_size_5 = 0, 0, 0, 0, 0
        count_le_5 = 0
        for sent_triples in all_triples_id:
            triples = set([tuple(sent_triples[i:i + 3]) for i in range(0, len(sent_triples), 3)])
            if len(triples) == 1:
                triples_size_1 += 1
            elif len(triples) == 2:
                triples_size_2 += 1
            elif len(triples) == 3:
                triples_size_3 += 1
            elif len(triples) == 4:
                triples_size_4 += 1
            else:
                triples_size_5 += 1
            if len(triples) <= 5:
                count_le_5 += 1
        print('Sentence number with 1, 2, 3_实体识别, 4_实体识别_1_3的O, >5 triplets: %d, %d, %d, %d, %d' % (triples_size_1, triples_size_2,
                                                                                    triples_size_3, triples_size_4,
                                                                                    triples_size_5))
        print('Sentence number with <= 5 triplets: %d' % count_le_5)


class WebNLGPrepare(Prepare):
    def process(self, data):
        all_sent_id, all_triples_id = data
        all_triples_id = change2relation_first(all_triples_id)
        standard_outputs = padding_triples(all_triples_id, self.config)
        sentence_length = [len(sent_id) for sent_id in all_sent_id]
        sentence_fw = padding_sentence(all_sent_id, self.config)
        sentence_bw = padding_sentence(inverse(all_sent_id), self.config)
        input_sentence_append_eos = append_eos2sentence(sentence_fw, self.config)
        relations_append_eos = append_eos2relations(len(sentence_fw), self.config)
        return [standard_outputs, sentence_length, sentence_fw, sentence_bw, [None] * len(sentence_fw),
                [None] * len(sentence_fw), input_sentence_append_eos, relations_append_eos, all_triples_id]

class CCKSPrepare():
    def __init__(self, config):
        self.config = config

    def load_words(self):
        with open(self.config.words2id_filename, 'r', encoding='utf-8') as f:
            s=eval(f.read())
        return json.loads(json.dumps(s))

    # def load_relations(self):
    #     return json.load(open(self.config.relations2id_filename, 'r'))
    def load_events(self):
        with open(self.config.event2id_filename, 'r', encoding='utf-8') as f:
            s = eval(f.read())
        return json.loads(json.dumps(s))
    def load_entitys(self):
        with open(self.config.entity2id_filename, 'r', encoding='utf-8') as f:
            s = eval(f.read())
        return json.loads(json.dumps(s))

    @staticmethod
    def remove_tone(s):
        s = unicodedata.normalize('NFD', s)
        cmb_chrs = dict.fromkeys(c for c in range(sys.maxunicode) if unicodedata.combining(unichr(c)))
        return s.translate(cmb_chrs)

    def load_data(self, name):
        if name.lower() == 'train':
            filename = self.config.train_filename
        elif name.lower() == 'test':
            filename = self.config.test_filename
        elif name.lower() == 'valid':
            filename = self.config.valid_filename
        else:
            print('name must be "train" or "test", but is %s' % name)
            raise ValueError
        print('loading %s' % filename)
        data = json.load(open(filename, 'r'))

        # print(len(data))
        print('data size %d' % (len(data[0])))
        return data

    def append_eos2events(self,sent_number, config):
        events_with_eos = range(config.words_number, config.words_number + config.event_number + 1)
        return [events_with_eos] * sent_number
    def padding_a_event_sentence(self,sent, beg, end):
        sent = list(sent)
        if len(sent) >= end - beg:#80
            return sent[beg: end]
        for i in range(end - beg - len(sent)):
            sent.append(0)
        return sent

    def padding(self,all_triples_id, seq_length, sent_index, inver_sent, config):
        all_triples = []
        all_sents = []
        all_inver_sents = []
        all_lengths=[]
        for events, length, sent, i_sent in zip(all_triples_id, seq_length, sent_index, inver_sent):
            padded, (beg, end) = self.padding_a_events(events, length, config)

            all_triples.append(padded)
            all_sents.append(self.padding_a_event_sentence(sent, beg, end))
            all_inver_sents.append(self.padding_a_event_sentence(i_sent, beg, end))
            if(length>config.max_sentence_length):
                all_lengths.append(config.max_sentence_length)
            else:
                all_lengths.append(length)
        return all_triples, all_sents, all_inver_sents,all_lengths




    def padding_a_events(self,events, length, config):
        """
        Pad triples to given length
        If the given triples is over length, then, randomly select some of it's triples
        :param triples:
        :return: padded triples
        """
        event_list = events[:]
        max_length = config.decoder_output_max_length
        triple_num = config.triple_number
        # print(max_length)

        events = [event_list[i * (length + 1):(i + 1) * (length + 1)] for i in
                  range(len(event_list) // (length + 1))]

        np.random.shuffle(events)
        padded = []
        min_beg = len(event_list)
        max_end = 0
        if (length <= config.max_sentence_length):
            min_beg = 1
            max_end = config.max_sentence_length + 1
            for t in events:
                padded.extend(t + [0] * (config.max_sentence_length + 1 - len(t)))

        else:
            for t in events:
                # print(t)
                d = np.array(t[1:])
                index = np.where(d > 0)[0]
                beg = index[0]
                end = index[-1]
                if (max_end < end):
                    max_end = end
                if (min_beg > beg):
                    min_beg = beg
            beg = min_beg + 1
            end = max_end + 2

            if (end-beg <= config.max_sentence_length):
                if (config.max_sentence_length // 2 + end <= length):
                    max_end = config.max_sentence_length // 2 + end
                    min_beg = max_end - config.max_sentence_length
                    if (min_beg < 1):
                        min_beg = 1
                        max_end = min_beg + config.max_sentence_length
                    # print(min_beg, max_end)
                else:
                    max_end = length
                    min_beg = length - config.max_sentence_length
            else:
                min_beg = beg
                max_end = beg + config.max_sentence_length
            for t in events:
                padded.extend(t[0:1] + t[min_beg:max_end])
        #
        #
        #
        #
        # # be_len=[]
        # for t in triples:
        #     if len(t)<=config.max_sentence_length+1:
        #         # padded.extend(t+[0]*(config.max_sentence_length+1-len(t)))
        #         pad.append([0,config.max_sentence_length])
        #         # print(len(t+[0]*(config.max_sentence_length+1-len(t))))
        #     else:
        #         #取中间部分，两边补0（O--无标记）
        #         d = np.array(t[1:])
        #         index = np.where(d > 0)[0]
        #         # print(index)
        #         beg = index[0]
        #         end = index[-1]
        #         # print(beg,end,t[beg],t[end])
        #         # print(config.max_sentence_length-(end+1-beg))
        #         if (end + 1 - beg <= config.max_sentence_length):#带标注的部分没有超过最长句子长度
        #             beg_index = (beg - (config.max_sentence_length - (end + 1 - beg)) // 2) if (beg - (
        #                         config.max_sentence_length - (end + 1 - beg)) // 2) > 0 else 1
        #             # print(beg_index)
        #             # r = t[beg_index:end + 2]
        #             if(len(t[beg_index:beg_index+config.max_sentence_length])==80):
        #                 # r = t[0:1] + t[beg_index:beg_index+config.max_sentence_length]
        #                 pad.append([beg-1, beg + config.max_sentence_length-1])
        #             else:
        #                 r=t[0:1]+t[-config.max_sentence_length:]
        #                 # print(len(t[len(t)-config.max_sentence_length: len(t) ]))
        #                 pad.append([len(t)-config.max_sentence_length, len(t) ])
        #             # print(r)
        #             # print(t[0:1], beg_index, beg_index + config.max_sentence_length, len(r))
        #         else:#带标注的部分超过最长句子长度
        #             # print(end-beg)
        #             # r = t[0:1] + t[beg:beg + config.max_sentence_length]
        #             pad.append([beg, beg + config.max_sentence_length])

        # padded.extend(r)

        # print(len(padded),max_length)
        #         print(len(t),min_beg,max_end,len(t[0:1]+t[min_beg:max_end]))

        if len(padded) >= max_length:
            padded = padded[: max_length]
        else:
            pad_event = list(config.NA_EVENT)
            # print(1,(max_length - len(triple_list)) // (config.max_sentence_length+1))
            for i in range((max_length - len(padded)) // (config.max_sentence_length + 1)):
                padded.extend(pad_event)
        # print(len(padded),max_length)
        # for i in range(triple_num):
        #     p=padded[i* (config.max_sentence_length + 1):(i+1)* (config.max_sentence_length + 1)]
        #     if(p[0]>30):
        #         print(p)
        assert len(padded) == max_length
        return padded, (min_beg - 1, max_end - 1)



    def process(self, data):
        all_sent_id, all_events_id = data
        # all_triples_id = change2relation_first(all_triples_id)
        sentence_length = [len(sent_id) for sent_id in all_sent_id]
        standard_outputs,sentence_fw,sentence_bw,all_lengths = self.padding(all_events_id , sentence_length,all_sent_id,inverse(all_sent_id),self.config)

        sentence_length=all_lengths
        input_sentence_append_eos = append_eos2sentence(sentence_fw, self.config)
        relations_append_eos = self.append_eos2events(len(sentence_fw), self.config)
        # for s in standard_outputs:
        #     for i in range(5):
        #         l=s[(i)*(config.max_sentence_length+1):(i+1)*(config.max_sentence_length+1)]
        #         if(l[0]>30):
        #             print(l)
        return [standard_outputs, sentence_length, sentence_fw, sentence_bw, [None] * len(sentence_fw),
                [None] * len(sentence_fw), input_sentence_append_eos, relations_append_eos, all_events_id ]

        # print(standard_outputs)
        # print(all_sent_id)
        # sentence_fw = padding_sentence(all_sent_id, self.config)
        # sentence_bw = padding_sentence(inverse(all_sent_id), self.config)
        #

    def test_padding(self, seq_length, sent_index, inver_sent, sentence_length,config):
        all_sents = []
        all_inver_sents = []
        for length, sent, i_sent in zip(seq_length, sent_index, inver_sent):
            beg = 0
            end = config.max_sentence_length
            all_sents.append(self.padding_a_event_sentence(sent, beg, end))
            all_inver_sents.append(self.padding_a_event_sentence(i_sent, beg, end))

        return all_sents, all_inver_sents
    def test_process(self, data):
        id,all_sent_id = data
        # all_triples_id = change2relation_first(all_triples_id)
        sentence_length = [len(sent_id) if len(sent_id)<=self.config.max_sentence_length else self.config.max_sentence_length for sent_id in all_sent_id]

        sentence_fw, sentence_bw = self.test_padding(sentence_length, all_sent_id,
                                                                      inverse(all_sent_id), sentence_length,self.config)

        input_sentence_append_eos = append_eos2sentence(sentence_fw, self.config)
        # relations_append_eos = self.append_eos2relations(len(sentence_fw), self.config)
        return [id, sentence_length, sentence_fw, sentence_bw, [None] * len(sentence_fw),
                [None] * len(sentence_fw), input_sentence_append_eos, id,id]



if __name__ == '__main__':
    # pass
    import const
    config_filename = './config.json'
    config = const.Config(config_filename=config_filename, cell_name='lstm', decoder_type='one')
    p=CCKSPrepare(config)
    data=p.load_data('test')
    # print(len(data))
    # for token,label in zip(data[0],data[1]):
    #     print(len(token), len(label))
    #     if(len(label)!=0):
    #         print(len(label)/(len(token)+1))
    #     for i in range(5):
    #
    #         if((i+1)*(len(token)+1)<=len(label)):
    #             l=label[i*(len(token)+1):(i+1)*(len(token)+1)]
    #             if(l[0]>=30):
    #                 print(l[0])

    p.test_process(data)
