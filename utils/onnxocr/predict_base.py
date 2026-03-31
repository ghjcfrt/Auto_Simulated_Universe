import onnxruntime


class PredictBase(object):
    def __init__(self, cpu=False):
        self.cpu = cpu

    def get_onnx_session(self, model_dir, use_gpu):
        if self.cpu:
            providers = ['CPUExecutionProvider']
        else:
            providers = onnxruntime.get_available_providers()
        sess_options = onnxruntime.SessionOptions()
        onnx_session = onnxruntime.InferenceSession(model_dir, providers=providers, sess_options=sess_options)

        return onnx_session


    def get_output_name(self, onnx_session):
        """获取模型输出节点名称列表。"""
        output_name = []
        for node in onnx_session.get_outputs():
            output_name.append(node.name)
        return output_name

    def get_input_name(self, onnx_session):
        """获取模型输入节点名称列表。"""
        input_name = []
        for node in onnx_session.get_inputs():
            input_name.append(node.name)
        return input_name

    def get_input_feed(self, input_name, image_numpy):
        """按输入名组装推理输入字典。"""
        input_feed = {}
        for name in input_name:
            input_feed[name] = image_numpy
        return input_feed
