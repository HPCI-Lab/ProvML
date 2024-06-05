
import os
import prov
import prov.model as prov
from datetime import datetime
# from mlflow.entities import Run
import getpass
import subprocess

from ..constants import PROV4ML_DATA
from ..datamodel.attribute_type import Prov4MLAttribute
from ..datamodel.artifact_data import artifact_is_pytorch_model
from ..provenance.context import Context

def create_prov_document() -> prov.ProvDocument:
    """
    Generates the first level of provenance for a given run.

    Args:
        run (Run): The run object.
        doc (prov.ProvDocument): The provenance document.

    Returns:
        prov.ProvDocument: The provenance document.
    """
    doc = prov.ProvDocument()

    #set namespaces
    doc.set_default_namespace(PROV4ML_DATA.USER_NAMESPACE)
    doc.add_namespace('prov','http://www.w3.org/ns/prov#')
    doc.add_namespace('xsd','http://www.w3.org/2000/10/XMLSchema#')
    doc.add_namespace('mlflow', 'mlflow') #TODO: find namespaces of mlflow and prov-ml ontologies
    doc.add_namespace('prov-ml', 'prov-ml')

    run_name = PROV4ML_DATA.EXPERIMENT_NAME # TODO: fix
    run_entity = doc.entity(f'{run_name}',other_attributes={
        "prov-ml:provenance_path":Prov4MLAttribute.get_attr(PROV4ML_DATA.PROV_SAVE_PATH),
        "prov-ml:artifact_uri":Prov4MLAttribute.get_attr(PROV4ML_DATA.ARTIFACTS_DIR),
        "prov-ml:run_id":Prov4MLAttribute.get_attr(PROV4ML_DATA.RUN_ID),
        "prov-ml:type": Prov4MLAttribute.get_attr("LearningStage"),
        "prov-ml:user_id": Prov4MLAttribute.get_attr(getpass.getuser()),
        # "prov:level": 1,
    })
        
    global_rank = os.getenv("SLURM_PROCID", None)
    if global_rank:
        node_rank = os.getenv("SLURM_NODEID", None)
        local_rank = os.getenv("SLURM_LOCALID", None) 
        run_entity.add_attributes({
            "prov-ml:global_rank":Prov4MLAttribute.get_attr(global_rank),
            "prov-ml:local_rank":Prov4MLAttribute.get_attr(local_rank),
            "prov-ml:node_rank":Prov4MLAttribute.get_attr(node_rank),
            # "prov:level": 1,
        })

    run_activity = doc.activity(f'{run_name}_execution', other_attributes={
        'prov-ml:type': Prov4MLAttribute.get_attr("LearningExecution"),
        # "prov:level": 1
    })
        #experiment entity generation
    experiment = doc.entity(PROV4ML_DATA.EXPERIMENT_NAME,other_attributes={
        "prov-ml:type": Prov4MLAttribute.get_attr("Experiment"),
        "prov-ml:experiment_name": Prov4MLAttribute.get_attr(PROV4ML_DATA.EXPERIMENT_NAME),
        # "mlflow:experiment_id": Prov4MLLOD.get_lv1_attr(run.info.experiment_id),
        # "prov:level": 1,
    })

    user_ag = doc.agent(f'{getpass.getuser()}',other_attributes={
        # "prov:level": 1,
    })
    doc.wasAssociatedWith(f'{run_name}_execution',user_ag,other_attributes={
        # "prov:level": 1,
    })
    doc.entity('source_code',{
        "prov-ml:type": Prov4MLAttribute.get_attr("SourceCode"),
        "prov-ml:source_name": Prov4MLAttribute.get_attr(__file__.split('/')[-1]),
        "prov-ml:source_type": Prov4MLAttribute.get_attr("LOCAL") if global_rank is None else Prov4MLAttribute.get_attr("SLURM"),
        # TODO: fix this
        # "mlflow:source_name": Prov4MLLOD.get_lv1_attr(run.data.tags['mlflow.source.name']),
        # "mlflow:source_type": Prov4MLLOD.get_lv1_attr(run.data.tags['mlflow.source.type']),
        # 'prov:level':1,   
    })

    try:
        # Run the git command to get the current commit hash
        commit_hash = subprocess.check_output(['git', 'rev-parse', 'HEAD']).strip().decode('utf-8')
        doc.activity('commit',other_attributes={
            "prov-ml:source_git_commit": Prov4MLAttribute.get_attr(commit_hash),
            # 'prov:level':1,
        })
        doc.wasGeneratedBy('source_code','commit',
                        #    other_attributes={'prov:level':1}
                           )
        doc.wasInformedBy(run_activity,'commit',
                        #   other_attributes={'prov:level':1}
                          )
    except:
        print("Git not found, skipping commit hash retrieval")
        doc.used(run_activity,'source_code',
                #  other_attributes={'prov:level':1}
                 )


    doc.hadMember(experiment,run_entity)
        # .add_attributes({'prov:level':1})
    doc.wasGeneratedBy(run_entity,run_activity,
                    #    other_attributes={'prov:level':1}
                       )

    for (name, ctx), metric in PROV4ML_DATA.metrics.items():
        if not doc.get_record(f'{name}_{ctx}'):
            metric_entity = doc.entity(f'{name}_{ctx}',{
                'prov-ml:type':Prov4MLAttribute.get_attr('Metric'),
                # 'prov:level':1,
            })
        else:
            metric_entity = doc.get_record(f'{name}_{ctx}')[0]

        for epoch, metric_per_epoch in metric.epochDataList.items():
            if ctx == Context.TRAINING: 
                if not doc.get_record(f'epoch_{epoch}'):
                    train_activity=doc.activity(f'epoch_{epoch}',other_attributes={
                    "prov-ml:type": Prov4MLAttribute.get_attr("TrainingExecution"),
                    # 'prov:level':1,
                    })
                    doc.wasStartedBy(train_activity,run_activity,other_attributes={'prov:level':1})

                for metric_value in metric_per_epoch:
                    metric_entity.add_attributes({
                        'prov-ml:step-value':Prov4MLAttribute.get_epoch_attr(epoch, metric_value),
                        'prov-ml:context': Prov4MLAttribute.get_attr(ctx),
                    })
                doc.wasGeneratedBy(metric_entity,f'epoch_{epoch}',
                                    # identifier=f'{name}_{epoch}_gen',
                                    identifier=f'{name}_train_{epoch}_gen',
                                    # other_attributes={'prov:level':1}
                                    )
                
            elif ctx == Context.VALIDATION:
                val_name = f'val_epoch_{epoch}'
                if not doc.get_record(val_name):
                    train_activity=doc.activity(val_name,other_attributes={
                    "prov-ml:type": Prov4MLAttribute.get_attr("ValidationExecution"),
                    # 'prov:level':1,
                    })
                    doc.wasStartedBy(train_activity,run_activity,other_attributes={'prov:level':1})

                for metric_value in metric_per_epoch:
                    metric_entity.add_attributes({
                        'prov-ml:step-value':Prov4MLAttribute.get_epoch_attr(epoch, metric_value),
                        'prov-ml:context': Prov4MLAttribute.get_attr(ctx),
                    })
                doc.wasGeneratedBy(metric_entity,val_name,
                                    # identifier=f'{name}_{epoch}_gen',
                                    identifier=f'{name}_val_{epoch}_gen',
                                    # other_attributes={'prov:level':1}
                                    )
                
            elif ctx == Context.EVALUATION:
                if not doc.get_record('test'):
                    eval_activity=doc.activity('test',other_attributes={
                    "prov-ml:type": Prov4MLAttribute.get_attr("TestingExecution"),
                    # 'prov:level':1,
                    })
                    doc.wasStartedBy(eval_activity,run_activity,other_attributes={'prov:level':1})

                for metric_value in metric_per_epoch:
                    metric_entity.add_attributes({
                        'prov-ml:step-value':Prov4MLAttribute.get_epoch_attr(epoch, metric_value),
                        'prov-ml:context': Prov4MLAttribute.get_attr(ctx),
                    })
                doc.wasGeneratedBy(metric_entity,'test',
                                    identifier=f'test_gen',
                                    # other_attributes={'prov:level':1}
                                    )

            else: 
                raise ValueError(f"Context {ctx} not recognized")

                        
    for name, param in PROV4ML_DATA.parameters.items():
        ent = doc.entity(f'{name}',{
            'prov-ml:value': Prov4MLAttribute.get_attr(param.value),
            'prov-ml:type': Prov4MLAttribute.get_attr('Parameter'),
            # 'prov:level':1,
        })
        doc.used(run_activity,ent,
                #  other_attributes={'prov:level':1}
                 )

    #dataset entities generation
    ent_ds = doc.entity(f'dataset',
                        # other_attributes={'prov:level':1}
                        )
    # for dataset_input in run.inputs.dataset_inputs:
    #     attributes={
    #         'prov-ml:type': Prov4MLAttribute.get_attr('Dataset'),
    #         'mlflow:digest': Prov4MLAttribute.get_attr(dataset_input.dataset.digest),
    #         # 'prov:level':1,
    #     }

    #     ent= doc.entity(f'{dataset_input.dataset.name}-{dataset_input.dataset.digest}',attributes)
    #     doc.used(run_activity,ent, 
    #             #  other_attributes={'prov:level':1}
    #              )
    #     doc.wasDerivedFrom(ent,ent_ds,identifier=f'{dataset_input.dataset.name}-{dataset_input.dataset.digest}_der',other_attributes={'prov:level':1})
    

    #model version entities generation
    model_version = PROV4ML_DATA.get_final_model()
    model_entity_label = model_version.path
    modv_ent=doc.entity(model_entity_label,{
        "prov-ml:type": Prov4MLAttribute.get_attr("ModelVersion"),
        'prov-ml:creation_epoch': Prov4MLAttribute.get_attr(model_version.step),
        'prov-ml:artifact_uri': Prov4MLAttribute.get_attr(model_version.path),
        'prov-ml:creation_timestamp': Prov4MLAttribute.get_attr(datetime.fromtimestamp(model_version.creation_timestamp / 1000)),
        'prov-ml:last_modified_timestamp': Prov4MLAttribute.get_attr(datetime.fromtimestamp(model_version.last_modified_timestamp / 1000)),
        # 'prov:level': 1
    })
    doc.wasGeneratedBy(modv_ent,run_activity,identifier=f'{model_entity_label}_gen',
                    #    other_attributes={'prov:level':1}
                       )
    
    model_ser = doc.activity(f'prov-ml:ModelRegistration',
                            #  other_attributes={'prov:level':1}
                             )
    doc.wasInformedBy(model_ser,run_activity,
    #                 #   other_attributes={'prov:level':1}
                      )
    doc.wasGeneratedBy(model_entity_label,model_ser,
    #                 #    other_attributes={'prov:level':1}
                       )
    
    for artifact in PROV4ML_DATA.get_model_versions()[:-1]: 
        doc.hadMember(model_entity_label,f"{artifact.path}")
            # .add_attributes({'prov:level':1})
    

    doc.activity("data_preparation",other_attributes={
        "prov-ml:type":"FeatureExtractionExecution",
        # 'prov:level':1,
    })
    #add attributes to dataset entities
    # for dataset_input in run.inputs.dataset_inputs:
    #     attributes={
    #         'mlflow:profile': Prov4MLAttribute.get_attr(dataset_input.dataset.profile),
    #         'mlflow:schema': Prov4MLAttribute.get_attr(dataset_input.dataset.schema),
    #     }
    #     ent= doc.get_record(f'{dataset_input.dataset.name}-{dataset_input.dataset.digest}')[0]
    #     ent.add_attributes(attributes)

    #     doc.wasGeneratedBy(ent,'data_preparation',
    #                     #    other_attributes={'prov:level':1}
    #                        )        #use two binary relation for yProv
    # doc.used('data_preparation','dataset',
    #         #  other_attributes={'prov:level':1}
    #          )
    
    #artifact entities generation
    for artifact in PROV4ML_DATA.get_artifacts():
        ent=doc.entity(f'{artifact.path}',{
            'prov-ml:artifact_path': Prov4MLAttribute.get_attr(artifact.path),
            # 'prov:level':1,
            #the FileInfo object stores only size and path of the artifact, specific connectors to the artifact store are needed to get other metadata
        })
        if artifact_is_pytorch_model(artifact):
            doc.wasGeneratedBy(f"{artifact.path}", model_ser,
                            #    other_attributes={'prov:level':1}
                               )
        else: 
            doc.wasGeneratedBy(ent,run_activity,identifier=f'{artifact.path}_gen',
                            #    other_attributes={'prov:level':1}
                            )    

    return doc
