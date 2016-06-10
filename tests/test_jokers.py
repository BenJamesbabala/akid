from akid.tests.test import TestCase, TestFactory, main
from akid import (
    IntegratedSensor,
    RescaleJoker,
    Survivor,
    GradientDescentKongFu
)
from akid.models.brains import AlexNet


class TestJoker(TestCase):
    def test_rescale_joker(self):
        # TODO(Shuai): This test is supposed to test on MNIST with integrated
        # sensor instead of using cifar10.
        brain = AlexNet(name="AlexNet")
        source = TestFactory.get_test_tf_source()

        sensor = IntegratedSensor(source_in=source,
                                  batch_size=128,
                                  val_batch_size=100,
                                  name='data')
        sensor.attach(RescaleJoker(name="rescale"), to_val=True)

        sensor.attach(RescaleJoker(name="rescale"))

        kid = Survivor(
            sensor,
            brain,
            GradientDescentKongFu(base_lr=0.1,
                                  decay_rate=0.1,
                                  decay_epoch_num=350),
            max_steps=2000)
        kid.setup()

        precision = kid.practice()
        assert precision >= 0.2


if __name__ == "__main__":
    main()
