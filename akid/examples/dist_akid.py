import tensorflow as tf

from akid import AKID_DATA_PATH
from akid import MNISTFeedSource
from akid import FeedSensor
from akid.models import OneLayerBrain

# Flags for defining the tf.train.ClusterSpec
tf.app.flags.DEFINE_string("ps_hosts", "",
                           "Comma-separated list of hostname:port pairs")
tf.app.flags.DEFINE_string("worker_hosts", "",
                           "Comma-separated list of hostname:port pairs")

# Flags for defining the tf.train.Server
tf.app.flags.DEFINE_string("job_name", "", "One of 'ps', 'worker'")
tf.app.flags.DEFINE_integer("task_index", 0, "Index of task within the job")

FLAGS = tf.app.flags.FLAGS


def main(_):
  ps_hosts = FLAGS.ps_hosts.split(",")
  worker_hosts = FLAGS.worker_hosts.split(",")

  # Create a cluster from the parameter server and worker hosts.
  cluster = tf.train.ClusterSpec({"ps": ps_hosts, "worker": worker_hosts})

  # Create and start a server for the local task.
  server = tf.train.Server(cluster,
                           job_name=FLAGS.job_name,
                           task_index=FLAGS.task_index)

  if FLAGS.job_name == "ps":
    server.join()
  elif FLAGS.job_name == "worker":

    # Assigns ops to the local worker by default.
    with tf.device(tf.train.replica_device_setter(
        worker_device="/job:worker/task:%d" % FLAGS.task_index,
        cluster=cluster)):

      # Build model...
      source = MNISTFeedSource(name="MNIST",
                               url='http://yann.lecun.com/exdb/mnist/',
                               work_dir=AKID_DATA_PATH + '/mnist',
                               center=True,
                               scale=True,
                               num_train=50000,
                               num_val=10000)
      sensor = FeedSensor(name='data', source_in=source)

      sensor.setup()
      brain = OneLayerBrain(name="brain")
      # input = [sensor.data()]
      # input.extend(sensor.labels())
      input = [sensor.data(), sensor.labels()]
      brain.setup(input)
      loss = brain.loss
      global_step = tf.Variable(0)

      train_op = tf.train.AdagradOptimizer(0.01).minimize(
        loss, global_step=global_step)

      saver = tf.train.Saver()
      summary_op = tf.summary.merge_all()
      init_op = tf.global_variables_initializer()

    # Create a "supervisor", which oversees the training process.
    sv = tf.train.Supervisor(is_chief=(FLAGS.task_index == 0),
                             logdir="/tmp/train_logs",
                             init_op=init_op,
                             summary_op=None,
                             saver=saver,
                             global_step=global_step,
                             save_model_secs=600)

    # The supervisor takes care of session initialization, restoring from
    # a checkpoint, and closing when done or an error occurs.
    with sv.managed_session(server.target) as sess:
      # Loop until the supervisor shuts down or 1000000 steps have completed.
      step = 0
      while not sv.should_stop() and step < 1000000:
        # Run a training step asynchronously.
        # See `tf.train.SyncReplicasOptimizer` for additional details on how to
        # perform *synchronous* training.
        loss_value, _, step = sess.run([loss, train_op, global_step],
                           feed_dict=sensor.fill_feed_dict())
        print loss_value

    # Ask for all the services to stop.
    sv.stop()

if __name__ == "__main__":
  tf.app.run()
