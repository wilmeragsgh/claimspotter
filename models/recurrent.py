import tensorflow as tf
import sys
from .adv_losses import adversarial_perturbation
sys.path.append('..')
from flags import FLAGS


class RecurrentModel:
    def __init__(self):
        pass

    def construct_model(self, x, x_len, output_mask, y, embed, kp_emb, kp_lstm, adv=False):
        yhat = self.fprop(x, x_len, output_mask, embed, kp_emb, kp_lstm, adv=False)
        loss = self.ce_loss(y, yhat)

        if adv:
            yhat = self.fprop(x, x_len, output_mask, embed, kp_emb, kp_lstm, loss, adv=True)
            loss = self.adv_loss(y, yhat)

        return yhat, loss

    def fprop(self, x, x_len, output_mask, embed, kp_emb, kp_lstm, ce_loss, adv):
        if adv:
            assert ce_loss is not None
        return self.build_lstm(x, x_len, output_mask, embed, kp_emb, kp_lstm, ce_loss, adv)

    def build_lstm(self, x, x_len, output_mask, embed, kp_emb, kp_lstm, ce_loss, adv):
        with tf.variable_scope('lstm', reuse=tf.AUTO_REUSE):
            x = tf.unstack(x, axis=1)
            for i in range(len(x)):
                x[i] = tf.nn.embedding_lookup(embed, x[i])
            x = tf.stack(x, axis=1)

            if adv:
                x = adversarial_perturbation(x, ce_loss)

            x = tf.nn.dropout(x, keep_prob=kp_emb)

            lstm = tf.nn.rnn_cell.MultiRNNCell([self.get_lstm(kp_lstm) for _ in range(FLAGS.rnn_num_layers)])
            output, state = tf.nn.dynamic_rnn(cell=lstm, inputs=x, sequence_length=x_len, dtype=tf.float32)

            add_weight = tf.get_variable('post_lstm_weight', shape=(FLAGS.rnn_cell_size, FLAGS.num_classes),
                                         initializer=tf.contrib.layers.xavier_initializer())
            add_bias = tf.get_variable('post_lstm_bias', shape=FLAGS.num_classes,
                                       initializer=tf.contrib.layers.xavier_initializer())

            return tf.matmul(tf.boolean_mask(output, output_mask), add_weight) + add_bias

    @staticmethod
    def get_lstm(kp_lstm):
        return tf.nn.rnn_cell.DropoutWrapper(
            tf.nn.rnn_cell.LSTMCell(FLAGS.rnn_cell_size),
            input_keep_prob=kp_lstm,
            state_keep_prob=kp_lstm,
            output_keep_prob=kp_lstm
        )

    @staticmethod
    def adv_loss(y, logits):
        return tf.identity(RecurrentModel.ce_loss(y, logits), name='adv_loss')

    @staticmethod
    def ce_loss(y, logits):
        loss = tf.nn.softmax_cross_entropy_with_logits_v2(labels=y, logits=logits)
        loss_l2 = 0

        if FLAGS.l2_reg_coeff > 0.0:
            varlist = tf.trainable_variables()
            loss_l2 = tf.add_n([tf.nn.l2_loss(v) for v in varlist if 'bias' not in v.name]) * FLAGS.l2_reg_coeff

        return tf.identity(loss + loss_l2, name='reg_loss')
