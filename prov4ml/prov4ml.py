import os
import mlflow
from mlflow import ActiveRun
from mlflow.entities import Metric,RunTag,Run
from mlflow.entities.file_info import FileInfo
from mlflow.utils.time import get_current_time_millis
from mlflow.utils.async_logging.run_operations import RunOperations
from lightning.pytorch.loggers import MLFlowLogger
import prov.model as prov
import prov.dot as dot

from datetime import datetime
from typing import Optional,Dict,Tuple,Any,List
from enum import Enum
from contextlib import contextmanager
from collections import namedtuple

from prov4ml import system_utils
from prov4ml import time_utils
from prov4ml import energy_utils

lv_attr = namedtuple('lv_attr', ['level', 'value'])
LVL_1 = "1"
LVL_2 = "2"

class Context(Enum):
    """Enumeration class for defining the context of the metric when saved using log_metrics.

    Attributes:
        TRAINING (str): The context for training metrics.
        EVALUATION (str): The context for evaluation metrics.
    """
    TRAINING = 'training'
    EVALUATION = 'evaluation'
    VALIDATION = 'validation'

def traverse_artifact_tree(
        client:mlflow.MlflowClient,
        run_id:str,path=None
        ) -> List[FileInfo]:
    """
    Recursively traverses the artifact tree of a given run in MLflow and returns a list of FileInfo objects.

    Args:
        client (mlflow.MlflowClient): The MLflow client object.
        run_id (str): The ID of the run.
        path (str, optional): The path to start the traversal from. Defaults to None.

    Returns:
        List[FileInfo]: A list of FileInfo objects representing the artifacts in the tree.
    """    
    artifact_list=client.list_artifacts(run_id,path)
    artifact_paths=[]
    for artifact in artifact_list:
        if artifact.is_dir:
            artifact_paths.extend(traverse_artifact_tree(client,run_id,artifact.path))
        else:
            artifact_paths.append(artifact)
    return artifact_paths

def log_metrics(
        metrics:Dict[str,Tuple[float,Context]],
        step:Optional[int]=None,
        synchronous:bool=True
        ) -> Optional[RunOperations]:
    """
    Logs the given metrics and their associated contexts to the active MLflow run.

    Parameters:
        metrics (Dict[str, Tuple[float, Context]]): A dictionary containing the metrics and their associated contexts.
        step (Optional[int]): The step number for the metrics. Defaults to None.
        synchronous (bool): Whether to log the metrics synchronously or asynchronously. Defaults to True.

    Returns:
        Optional[RunOperations]: The run operations object if logging is successful, None otherwise.
    """
    #create two separate lists, one for metrics and one for tags, and log them together using native log.batch
    client= mlflow.MlflowClient()

    timestamp=get_current_time_millis()
    metrics_arr=[Metric(key,value,timestamp,step or 0) for key,(value,context) in metrics.items()]
    tag_arr=[RunTag(f'metric.context.{key}',context.name) for key,(value,context) in metrics.items()]

    return client.log_batch(mlflow.active_run().info.run_id,metrics=metrics_arr,tags=tag_arr,synchronous=synchronous)

def log_metric(key: str, value: float, context:Context, step: Optional[int] = None, synchronous: bool = True, timestamp: Optional[int] = None) -> Optional[RunOperations]:
    """
    Logs a metric with the specified key, value, and context.

    Args:
        key (str): The key of the metric.
        value (float): The value of the metric.
        context (Context): The context of the metric.
        step (Optional[int], optional): The step of the metric. Defaults to None.
        synchronous (bool, optional): Whether to log the metric synchronously. Defaults to True.
        timestamp (Optional[int], optional): The timestamp of the metric. Defaults to None.

    Returns:
        Optional[RunOperations]: The run operations object.

    """
    client = mlflow.MlflowClient()
    client.set_tag(mlflow.active_run().info.run_id,f'metric.context.{key}',context.name)
    return client.log_metric(mlflow.active_run().info.run_id,key,value,step=step or 0,synchronous=synchronous,timestamp=timestamp or get_current_time_millis())

def log_current_execution_time(label: str, context : Context, step:Optional[int]=None) -> None:
    return log_metric(label, time_utils.get_time(), context, step=step)

def log_param(key: str, value: Any) -> None:
    return mlflow.log_param(key, value)

def log_params(params: Dict[str, Any]) -> None:
    return mlflow.log_params(params)

def log_model(model, model_name="default") -> None:
    return mlflow.pytorch.log_model(
        pytorch_model=model,
        artifact_path=mlflow.active_run().info.run_name,
        registered_model_name=model_name
        )

def log_system_metrics(
        context : Context, 
        step: Optional[int] = None, 
        synchronous: bool = True, 
        timestamp: Optional[int] = None
        ) -> None:
    """
    Logs system metrics to the active MLflow run.

    Args:
        step (Optional[int], optional): The step of the metrics. Defaults to None.
    
    Returns:
        None
    """
    client = mlflow.MlflowClient()
    client.set_tag(mlflow.active_run().info.run_id,'metric.context.cpu_usage',context.name)
    client.log_metric(mlflow.active_run().info.run_id, "cpu_usage", system_utils.get_cpu_usage(), step=step, synchronous=synchronous,timestamp=timestamp or get_current_time_millis())
    client.set_tag(mlflow.active_run().info.run_id,'metric.context.memory_usage',context.name)
    client.log_metric(mlflow.active_run().info.run_id, "memory_usage", system_utils.get_memory_usage(), step=step, synchronous=synchronous,timestamp=timestamp or get_current_time_millis())
    client.set_tag(mlflow.active_run().info.run_id,'metric.context.disk_usage',context.name)
    client.log_metric(mlflow.active_run().info.run_id, "disk_usage", system_utils.get_disk_usage(), step=step, synchronous=synchronous,timestamp=timestamp or get_current_time_millis())
    client.set_tag(mlflow.active_run().info.run_id,'metric.context.gpu_memory_usage',context.name)
    client.log_metric(mlflow.active_run().info.run_id, "gpu_memory_usage", system_utils.get_gpu_memory_usage(), step=step, synchronous=synchronous,timestamp=timestamp or get_current_time_millis())
    client.set_tag(mlflow.active_run().info.run_id,'metric.context.gpu_usage',context.name)
    client.log_metric(mlflow.active_run().info.run_id, "gpu_usage", system_utils.get_gpu_usage(), step=step, synchronous=synchronous,timestamp=timestamp or get_current_time_millis())

def log_carbon_metrics(
    context : Context, 
    step: Optional[int] = None, 
    synchronous: bool = True, 
    timestamp: Optional[int] = None
    ) -> Tuple[float, float]:
    
    emissions = energy_utils.stop_carbon_tracked_block()
   
    client = mlflow.MlflowClient()
    client.set_tag(mlflow.active_run().info.run_id,'metric.context.emissions',context.name)
    client.log_metric(mlflow.active_run().info.run_id, "emissions", emissions.energy_consumed, step=step, synchronous=synchronous,timestamp=timestamp or get_current_time_millis())
    client.set_tag(mlflow.active_run().info.run_id,'metric.context.emissions_rate',context.name)
    client.log_metric(mlflow.active_run().info.run_id, "emissions_rate", emissions.emissions_rate, step=step, synchronous=synchronous,timestamp=timestamp or get_current_time_millis())
    client.set_tag(mlflow.active_run().info.run_id,'metric.context.cpu_power',context.name)
    client.log_metric(mlflow.active_run().info.run_id, "cpu_power", emissions.cpu_power, step=step, synchronous=synchronous,timestamp=timestamp or get_current_time_millis())
    client.set_tag(mlflow.active_run().info.run_id,'metric.context.gpu_power',context.name)
    client.log_metric(mlflow.active_run().info.run_id, "gpu_power", emissions.gpu_power, step=step, synchronous=synchronous,timestamp=timestamp or get_current_time_millis())
    client.set_tag(mlflow.active_run().info.run_id,'metric.context.ram_power',context.name)
    client.log_metric(mlflow.active_run().info.run_id, "ram_power", emissions.ram_power, step=step, synchronous=synchronous,timestamp=timestamp or get_current_time_millis())
    client.set_tag(mlflow.active_run().info.run_id,'metric.context.cpu_energy',context.name)
    client.log_metric(mlflow.active_run().info.run_id, "cpu_energy", emissions.cpu_energy, step=step, synchronous=synchronous,timestamp=timestamp or get_current_time_millis())
    client.set_tag(mlflow.active_run().info.run_id,'metric.context.gpu_energy',context.name)
    client.log_metric(mlflow.active_run().info.run_id, "gpu_energy", emissions.gpu_energy, step=step, synchronous=synchronous,timestamp=timestamp or get_current_time_millis())
    client.set_tag(mlflow.active_run().info.run_id,'metric.context.ram_energy',context.name)
    client.log_metric(mlflow.active_run().info.run_id, "ram_energy", emissions.ram_energy, step=step, synchronous=synchronous,timestamp=timestamp or get_current_time_millis())
    client.set_tag(mlflow.active_run().info.run_id,'metric.context.energy_consumed',context.name)
    client.log_metric(mlflow.active_run().info.run_id, "energy_consumed", emissions.energy_consumed, step=step, synchronous=synchronous,timestamp=timestamp or get_current_time_millis())

def first_level_prov(run:Run, doc: prov.ProvDocument) -> prov.ProvDocument:
    """
    Generates the first level of provenance for a given run.

    Args:
        run (Run): The run object.
        doc (prov.ProvDocument): The provenance document.

    Returns:
        prov.ProvDocument: The provenance document.
    """
    client = mlflow.MlflowClient()

    #run entity and activity generation

    run_entity = doc.entity(f'{run.info.run_name}',other_attributes={
        "mlflow:run_id": str(lv_attr(LVL_1,str(run.info.run_id))),
        "mlflow:artifact_uri":str(lv_attr(LVL_1,str(run.info.artifact_uri))),
        "prov-ml:type":str(lv_attr(LVL_1,"LearningStage")),
        "mlflow:user_id":str(lv_attr(LVL_1,str(run.info.user_id))),
        "prov:level":LVL_1
    })

    run_activity = doc.activity(f'{run.info.run_name}_execution',
                                #datetime.fromtimestamp(run.info.start_time/1000),
                                #datetime.fromtimestamp(run.info.end_time/1000),
                                other_attributes={
        'prov-ml:type':str(lv_attr(LVL_1,'LearningStageExecution')),
        "prov:level":LVL_1
    })
    #experiment entity generation
    experiment = doc.entity(f'{client.get_experiment(run.info.experiment_id).name}',other_attributes={
        "prov-ml:type":str(lv_attr(LVL_1,"LearningExperiment")),
        "mlflow:experiment_id": str(lv_attr(LVL_1,str(run.info.experiment_id))),
        "prov:level":LVL_1
    })

    doc.hadMember(experiment,run_entity).add_attributes({
        'prov:level':LVL_1
    })
    doc.wasGeneratedBy(run_entity,run_activity,other_attributes={
        'prov:level':LVL_1
    })


    #metrics and params generation
    for name,_ in run.data.metrics.items():
        #the Run object stores only the most recent metrics, to get all metrics lower level API is needed
        for metric in client.get_metric_history(run.info.run_id,name):
            i=0
            ent=doc.entity(f'{name}_{metric.step or i}',{
                'prov-ml:type':'ModelEvaluation',
                'mlflow:value':str(lv_attr(LVL_1,metric.value)),
                'mlflow:step':str(lv_attr(LVL_1,metric.step or i)),
                'prov:level':LVL_1,
            })
            doc.wasGeneratedBy(ent,run_activity,
                               #datetime.fromtimestamp(metric.timestamp/1000),
                               identifier=f'{name}_{metric.step}_gen',
                               other_attributes={
                                    'prov:level':LVL_1
                               })
            i+=1

    for name,value in run.data.params.items():
        ent = doc.entity(f'{name}',{
            'mlflow:value':str(lv_attr(LVL_1,value)),
            'prov-ml:type':str(lv_attr(LVL_1,'LearningHyperparameterValue')),
            'prov:level':LVL_1,
        })
        doc.used(run_activity,ent,other_attributes={'prov:level':LVL_1})

    #dataset entities generation
    ent_ds = doc.entity(f'dataset',other_attributes={'prov:level':LVL_1})
    for dataset_input in run.inputs.dataset_inputs:
        attributes={
            'prov-ml:type':str(lv_attr(LVL_1,'FeatureSetData')),
            'mlflow:digest':str(lv_attr(LVL_1,str(dataset_input.dataset.digest))),
            'prov:level':LVL_1,
        }

        ent= doc.entity(f'{dataset_input.dataset.name}-{dataset_input.dataset.digest}',attributes)
        doc.used(run_activity,ent, other_attributes={'prov:level':LVL_1})
        doc.wasDerivedFrom(ent,ent_ds,identifier=f'{dataset_input.dataset.name}-{dataset_input.dataset.digest}_der',other_attributes={'prov:level':LVL_1})
    

    #model version entities generation
    model_version = client.search_model_versions(f'run_id="{run.info.run_id}"')[0] #only one model version per run (in this case)

    modv_ent=doc.entity(f'{model_version.name}_{model_version.version}',{
        "prov-ml:type":str(lv_attr(LVL_1,"Model")),
        'mlflow:version':str(lv_attr(LVL_1,model_version.version)),
        'mlflow:artifact_uri':str(lv_attr(LVL_1,model_version.source)),
        'mlflow:creation_timestamp':str(lv_attr(LVL_1,datetime.fromtimestamp(model_version.creation_timestamp/1000))),
        'mlflow:last_updated_timestamp':str(lv_attr(LVL_1,datetime.fromtimestamp(model_version.last_updated_timestamp/1000))),
        'prov:level':LVL_1
    })
    doc.wasGeneratedBy(modv_ent,run_activity,identifier=f'{model_version.name}_{model_version.version}_gen',other_attributes={'prov:level':LVL_1})
    
    
    #get the model registered in the model registry of mlflow
    model = client.get_registered_model(model_version.name)
    mod_ent=doc.entity(f'{model.name}',{
        "prov-ml:type":str(lv_attr(LVL_1,"Model")),
        'mlflow:creation_timestamp':str(lv_attr(LVL_1,datetime.fromtimestamp(model.creation_timestamp/1000))),
        'prov:level':LVL_1,
    })
    spec=doc.specializationOf(modv_ent,mod_ent)
    spec.add_attributes({'prov:level':LVL_1})   #specilizationOf doesn't accept other_attributes, but its cast as record does


    #artifact entities generation
    artifacts=traverse_artifact_tree(client,run.info.run_id)
    for artifact in artifacts:
        ent=doc.entity(f'{artifact.path}',{
            'mlflow:artifact_path':str(lv_attr(LVL_1,artifact.path)),
            'prov:level':LVL_1,
            #the FileInfo object stores only size and path of the artifact, specific connectors to the artifact store are needed to get other metadata
        })
        doc.wasGeneratedBy(ent,run_activity,identifier=f'{artifact.path}_gen',other_attributes={'prov:level':LVL_1})
    

    return doc

def second_level_prov(run:Run, doc: prov.ProvDocument) -> prov.ProvDocument:
    """
    Generates the second level of provenance for a given run.
    Args:
        run (Run): The run object.
        doc (prov.ProvDocument): The provenance document.
    Returns:
        prov.ProvDocument: The provenance document.
    """
    client = mlflow.MlflowClient()
        
    run_activity= doc.get_record(f'{run.info.run_name}_execution')[0]
    run_activity.add_attributes({
        "mlflow:status":str(lv_attr(LVL_2,run.info.status)),
        "mlflow:lifecycle_stage":str(lv_attr(LVL_2,run.info.lifecycle_stage)),
    })
    user_ag = doc.agent(f'{run.info.user_id}',other_attributes={
        "prov:level":LVL_2,
    })
    doc.wasAssociatedWith(f'{run.info.run_name}_execution',user_ag,other_attributes={
        "prov:level":LVL_2,
    })

    doc.entity('source_code',{
        "mlflow:source_name":str(lv_attr(LVL_2,run.data.tags['mlflow.source.name'])),
        "mlflow:source_type":str(lv_attr(LVL_2,run.data.tags['mlflow.source.type'])),  
        'prov:level':LVL_2,   
    })

    if 'mlflow.source.git.commit' in run.data.tags.keys():
        doc.activity('commit',other_attributes={
            "mlflow:source_git_commit":str(lv_attr(LVL_2,run.data.tags['mlflow.source.git.commit'])),
            'prov:level':LVL_2,
        })
        doc.wasGeneratedBy('source_code','commit',other_attributes={'prov:level':LVL_2})
        doc.wasInformedBy(run_activity,'commit',other_attributes={'prov:level':LVL_2})
    else:
        doc.used(run_activity,'source_code',other_attributes={'prov:level':LVL_2})

    #remove relations between metrics and run


    #create activities for training and evaluation and associate metrics

    for name,_ in run.data.metrics.items():
        for metric in client.get_metric_history(run.info.run_id,name):
            if not doc.get_record(f'train_step_{metric.step}'):
                train_activity=doc.activity(f'train_step_{metric.step}',other_attributes={
                "prov-ml:type":str(lv_attr(LVL_2,"TrainingExecution")),
                'prov:level':LVL_2,
                })
                test_activity=doc.activity(f'test_step_{metric.step}',other_attributes={
                    "prov-ml:type":str(lv_attr(LVL_2,"EvaluationExecution")),
                    'prov:level':LVL_2,
                })
                doc.wasStartedBy(train_activity,run_activity,other_attributes={'prov:level':LVL_2})
                doc.wasStartedBy(test_activity,run_activity,other_attributes={'prov:level':LVL_2})

            # if doc.get_record(f'{name}_{metric.step}_gen')[0]:
            #     doc._records.remove(doc.get_record(f'{name}_{metric.step}_gen')[0]) #accessing private attribute, propriety doesn't allow to remove records, but we need to remove the lv1 generation
            if run.data.tags[f'metric.context.{metric.key}']==Context.TRAINING.name:
                doc.wasGeneratedBy(f'{metric.key}_{metric.step}',f'train_step_{metric.step}',other_attributes={'prov:level':LVL_2})    
            elif run.data.tags[f'metric.context.{metric.key}']==Context.EVALUATION.name:
                doc.wasGeneratedBy(f'{metric.key}_{metric.step}',f'test_step_{metric.step}',other_attributes={'prov:level':LVL_2})
    
    #data transformation activity
    doc.activity("data_preparation",other_attributes={
        "prov-ml:type":"FeatureExtractionExecution",
        'prov:level':LVL_2,
    })
    #add attributes to dataset entities
    for dataset_input in run.inputs.dataset_inputs:
        attributes={
            'mlflow:profile':str(lv_attr(LVL_2,dataset_input.dataset.profile)),
            'mlflow:schema':str(lv_attr(LVL_2,dataset_input.dataset.schema)),   
        }
        ent= doc.get_record(f'{dataset_input.dataset.name}-{dataset_input.dataset.digest}')[0]
        ent.add_attributes(attributes)

        #remove old generation relationship
        # if doc.get_record(f'{dataset_input.dataset.name}-{dataset_input.dataset.digest}_der')[0]:
        #     doc._records.remove(doc.get_record(f'{dataset_input.dataset.name}-{dataset_input.dataset.digest}_der')[0])
        #doc.wasDerivedFrom(ent,'dataset','data_preparation',other_attributes={'prov:level':LVL_2})  #use new transform activity for derivation
        doc.wasGeneratedBy(ent,'data_preparation',other_attributes={'prov:level':LVL_2})        #use two binary relation for yProv
    doc.used('data_preparation','dataset',other_attributes={'prov:level':LVL_2})
    # doc.get_record('dataset')[0].add_attributes({
    #     'source_mirror':str(run.inputs.dataset_inputs[0].tags[1]),
    # })
    
    model_version = client.search_model_versions(f'run_id="{run.info.run_id}"')[0]
    # if doc.get_record(f'{model_version.name}_{model_version.version}_gen')[0]:
    #     doc._records.remove(doc.get_record(f'{model_version.name}_{model_version.version}_gen')[0])

    model_ser = doc.activity(f'mlflow:ModelRegistration',other_attributes={'prov:level':LVL_2})
    doc.wasInformedBy(model_ser,run_activity,other_attributes={'prov:level':LVL_2})
    doc.wasGeneratedBy(f'{model_version.name}_{model_version.version}',model_ser,other_attributes={'prov:level':LVL_2})
    
    for artifact in traverse_artifact_tree(client,run.info.run_id,model_version.name): #get artifacts whose path starts with TinyVGG: these are model serialization and metadata files
        # if doc.get_record(f'{artifact.path}_gen'):
        #     doc._records.remove(doc.get_record(f'{artifact.path}_gen')[0])
        memb=doc.hadMember(f'{model_version.name}_{model_version.version}',f"{artifact.path}")
        memb.add_attributes({'prov:level':LVL_2})
    return doc

@contextmanager
def start_run_ctx(
    prov_user_namespace:str,
    path: Optional[str] = None,
    run_id: Optional[str] = None,
    experiment_id: Optional[str] = None,
    run_name: Optional[str] = None,
    nested: bool = False,
    tags: Optional[Dict[str, Any]] = None,
    description: Optional[str] = None,
    log_system_metrics: Optional[bool] = None,) -> ActiveRun: # type: ignore
    """
    Starts an MLflow run and generates provenance information.

    Args:
        prov_user_namespace (str): The namespace of the user, this will be used as the default namespace.
        run_id (Optional[str]): The ID of the run to start. If not provided, a new run ID will be generated.
        experiment_id (Optional[str]): The ID of the experiment to associate the run with. If not provided, the default experiment will be used.
        run_name (Optional[str]): The name of the run. If not provided, a default name will be assigned.
        nested (bool): Whether the run is nested within another run. Defaults to False.
        tags (Optional[Dict[str, Any]]): Additional tags to associate with the run. Defaults to None.
        description (Optional[str]): A description of the run. Defaults to None.
        log_system_metrics (Optional[bool]): Whether to log system metrics. Defaults to None.

    Returns:
        ActiveRun: The active run object.

    Raises:
        None

    """
    #wrapper for mlflow.start_run, with prov generation
    
    active_run= mlflow.start_run(run_id,experiment_id,run_name,nested,tags,description,log_system_metrics)
    print('started run', active_run.info.run_id)
    yield active_run #return the mlflow context manager, same one as mlflow.start_run()

    run_id=active_run.info.run_id
    mlflow.end_run() #end the run, as per mlflow documentation
    print('ended run')

    print('doc generation')

    client = mlflow.MlflowClient()
    active_run=client.get_run(run_id)

    doc = prov.ProvDocument()

    #set namespaces
    doc.set_default_namespace(prov_user_namespace)
    doc.add_namespace('prov','http://www.w3.org/ns/prov#')
    doc.add_namespace('xsd','http://www.w3.org/2000/10/XMLSchema#')
    
    doc.add_namespace('mlflow', 'mlflow') #TODO: find namespaces of mlflow and prov-ml ontologies
    doc.add_namespace('prov-ml', 'prov-ml')

    doc = first_level_prov(active_run,doc)
    doc = second_level_prov(active_run,doc)    

    #datasets are associated with two sets of tags: input tags, of the DatasetInput object, and the tags of the dataset itself
    # for input_tag in dataset_input.tags:
    #     attributes[f'mlflow:{input_tag.key.strip("mlflow.")}']=str(input_tag.value)
    # for key,value in ds_tags['tags'].items():
    #     attributes[f'mlflow:{str(key).strip("mlflow.")}']=str(value)

    graph_filename = f'provgraph_{run_id}.json'
    dot_filename = f'provgraph_{run_id}.dot'
    path_graph = "/".join([path, graph_filename]) if path else graph_filename
    path_dot = "/".join([path, dot_filename]) if path else dot_filename

    with open(path_graph,'w') as prov_graph:
        doc.serialize(prov_graph)
    with open(path_dot, 'w') as prov_dot:
        prov_dot.write(dot.prov_to_dot(doc).to_string())

def start_run(
    prov_user_namespace:str,
    experiment_name: Optional[str] = None,
    provenance_save_dir: Optional[str] = None,
    mlflow_save_dir: Optional[str] = None,
    nested: bool = False,
    tags: Optional[Dict[str, Any]] = None,
    description: Optional[str] = None,
    log_system_metrics: Optional[bool] = None
    ):

    global USER_NAMESPACE, PROV_SAVE_PATH, MLFLOW_SAVE_PATH

    if mlflow_save_dir:
        mlflow.set_tracking_uri(mlflow_save_dir)

    exp = mlflow.get_experiment_by_name(name=experiment_name)
    if not exp:
        if mlflow_save_dir: 
            experiment_id = mlflow.create_experiment(
                name=experiment_name,
                artifact_location=mlflow_save_dir 
            )
        else: 
            experiment_id = mlflow.create_experiment(name=experiment_name)
    else:
        experiment_id = exp.experiment_id

    mlflow.set_experiment(experiment_name)
    mlflow.pytorch.autolog()

    mlflow.start_run(
        experiment_id=experiment_id,
        run_name=mlflow_save_dir,
        nested=nested,
        tags=tags,
        description=description,
        log_system_metrics=log_system_metrics, 
    )

    energy_utils._carbon_init()
    # start_carbon_logging()

    USER_NAMESPACE = prov_user_namespace
    PROV_SAVE_PATH = provenance_save_dir
    MLFLOW_SAVE_PATH = mlflow_save_dir

def end_run(): 

    run_id=mlflow.active_run().info.run_id
    
    mlflow.end_run() #end the run, as per mlflow documentation

    client = mlflow.MlflowClient()
    active_run=client.get_run(run_id)

    doc = prov.ProvDocument()

    #set namespaces
    doc.set_default_namespace(USER_NAMESPACE)
    doc.add_namespace('prov','http://www.w3.org/ns/prov#')
    doc.add_namespace('xsd','http://www.w3.org/2000/10/XMLSchema#')
    doc.add_namespace('mlflow', 'mlflow') #TODO: find namespaces of mlflow and prov-ml ontologies
    doc.add_namespace('prov-ml', 'prov-ml')

    doc = first_level_prov(active_run,doc)
    doc = second_level_prov(active_run,doc)    

    #datasets are associated with two sets of tags: input tags, of the DatasetInput object, and the tags of the dataset itself
    # for input_tag in dataset_input.tags:
    #     attributes[f'mlflow:{input_tag.key.strip("mlflow.")}']=str(input_tag.value)
    # for key,value in ds_tags['tags'].items():
    #     attributes[f'mlflow:{str(key).strip("mlflow.")}']=str(value)

    graph_filename = f'provgraph_{run_id}.json'
    dot_filename = f'provgraph_{run_id}.dot'
    path_graph = "/".join([PROV_SAVE_PATH, graph_filename]) if PROV_SAVE_PATH else graph_filename
    path_dot = "/".join([PROV_SAVE_PATH, dot_filename]) if PROV_SAVE_PATH else dot_filename

    if PROV_SAVE_PATH and not os.path.exists(PROV_SAVE_PATH):
        os.makedirs(PROV_SAVE_PATH)

    with open(path_graph,'w') as prov_graph:
        doc.serialize(prov_graph)
    with open(path_dot, 'w') as prov_dot:
        prov_dot.write(dot.prov_to_dot(doc).to_string())

def get_mlflow_logger(): 
    mlf_logger = MLFlowLogger(
        experiment_name=mlflow.get_experiment(
            mlflow.active_run().info.experiment_id
        ).name,
        artifact_location=mlflow.get_artifact_uri(), 
        run_id=mlflow.active_run().info.run_id,
        save_dir=MLFLOW_SAVE_PATH, 
        log_model="all",
    )

    return mlf_logger

def get_run_id(): 
    return mlflow.active_run().info.run_id
