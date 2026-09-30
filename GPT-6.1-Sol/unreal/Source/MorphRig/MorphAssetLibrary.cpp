#include "MorphAssetLibrary.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/SkeletalMeshSocket.h"
#include "Animation/Skeleton.h"
#include "Animation/MorphTarget.h"
#include "Animation/AnimSequence.h"
#include "Rendering/SkeletalMeshRenderData.h"
#include "Rendering/SkinWeightVertexBuffer.h"
#include "Serialization/JsonSerializer.h"

void UMorphAssetLibrary::AddAssetSocket(USkeletalMesh* Mesh,FName SocketName,FName BoneName,FVector Offset)
{
    if(!Mesh||!Mesh->GetSkeleton())return;
    USkeletalMeshSocket* Socket=Mesh->GetSkeleton()->FindSocket(SocketName);
    if(!Socket){Socket=NewObject<USkeletalMeshSocket>(Mesh->GetSkeleton(),SocketName);Mesh->GetSkeleton()->Sockets.Add(Socket);}
    Socket->SocketName=SocketName;Socket->BoneName=BoneName;Socket->RelativeLocation=Offset;
    Mesh->GetSkeleton()->MarkPackageDirty();Mesh->MarkPackageDirty();
}

void UMorphAssetLibrary::AddAssetSocketAtComponentPosition(USkeletalMesh* Mesh,FName SocketName,FName BoneName,FVector Position)
{
    if(!Mesh)return;
    const FReferenceSkeleton& Ref=Mesh->GetRefSkeleton();
    int32 Index=Ref.FindBoneIndex(BoneName);if(Index<0)return;
    FTransform Component=Ref.GetRefBonePose()[Index];
    while((Index=Ref.GetParentIndex(Index))>=0)Component=Component*Ref.GetRefBonePose()[Index];
    AddAssetSocket(Mesh,SocketName,BoneName,Component.InverseTransformPosition(Position));
}

FString UMorphAssetLibrary::InspectSkeletalAsset(USkeletalMesh* Mesh)
{
    if(!Mesh)return TEXT("{}");
    TSharedRef<FJsonObject> Object=MakeShared<FJsonObject>();
    const FBoxSphereBounds Bounds=Mesh->GetImportedBounds();
    Object->SetNumberField(TEXT("height_cm"),Bounds.BoxExtent.Z*2);
    const FReferenceSkeleton& Ref=Mesh->GetRefSkeleton();
    Object->SetNumberField(TEXT("bone_count"),Ref.GetNum());
    TArray<TSharedPtr<FJsonValue>> Bones,Roots,Morphs,LODs,MorphLODs;
    TArray<FTransform> Component;Component.SetNum(Ref.GetNum());
    for(int32 I=0;I<Ref.GetNum();++I)
    {
        const int32 Parent=Ref.GetParentIndex(I);Component[I]=Parent>=0?Ref.GetRefBonePose()[I]*Component[Parent]:Ref.GetRefBonePose()[I];
        TSharedRef<FJsonObject> B=MakeShared<FJsonObject>();B->SetStringField(TEXT("name"),Ref.GetBoneName(I).ToString());
        B->SetStringField(TEXT("parent"),Parent>=0?Ref.GetBoneName(Parent).ToString():TEXT("None"));
        B->SetArrayField(TEXT("position_cm"),{MakeShared<FJsonValueNumber>(Component[I].GetLocation().X),MakeShared<FJsonValueNumber>(Component[I].GetLocation().Y),MakeShared<FJsonValueNumber>(Component[I].GetLocation().Z)});
        Bones.Add(MakeShared<FJsonValueObject>(B));if(Parent<0)Roots.Add(MakeShared<FJsonValueString>(Ref.GetBoneName(I).ToString()));
    }
    for(UMorphTarget* Morph:Mesh->GetMorphTargets())
    {
        Morphs.Add(MakeShared<FJsonValueString>(Morph->GetName()));
        TSharedRef<FJsonObject> Entry=MakeShared<FJsonObject>();Entry->SetStringField(TEXT("name"),Morph->GetName());
        TArray<TSharedPtr<FJsonValue>> Counts;for(const FMorphTargetLODModel& L:Morph->GetMorphLODModels())Counts.Add(MakeShared<FJsonValueNumber>(L.Vertices.Num()));
        Entry->SetArrayField(TEXT("delta_vertices_by_lod"),Counts);MorphLODs.Add(MakeShared<FJsonValueObject>(Entry));
    }
    if(const FSkeletalMeshRenderData* Render=Mesh->GetResourceForRendering())for(int32 I=0;I<Render->LODRenderData.Num();++I)
    {
        const FSkeletalMeshLODRenderData& L=Render->LODRenderData[I];TSharedRef<FJsonObject> Item=MakeShared<FJsonObject>();
        Item->SetNumberField(TEXT("lod"),I);Item->SetNumberField(TEXT("vertices"),L.GetNumVertices());
        Item->SetNumberField(TEXT("triangles"),L.MultiSizeIndexContainer.GetIndexBuffer()->Num()/3);
        Item->SetNumberField(TEXT("sections"),L.RenderSections.Num());
        TArray<TSharedPtr<FJsonValue>> Sections;for(const FSkelMeshRenderSection& Section:L.RenderSections)Sections.Add(MakeShared<FJsonValueNumber>(Section.MaterialIndex));
        Item->SetArrayField(TEXT("section_material_indices"),Sections);LODs.Add(MakeShared<FJsonValueObject>(Item));
    }
    Object->SetArrayField(TEXT("bones"),Bones);Object->SetArrayField(TEXT("root_bones"),Roots);Object->SetArrayField(TEXT("morph_targets"),Morphs);Object->SetArrayField(TEXT("lods"),LODs);
    Object->SetArrayField(TEXT("morph_lod_data"),MorphLODs);
    FString Text;FJsonSerializer::Serialize(Object,TJsonWriterFactory<>::Create(&Text));return Text;
}

FString UMorphAssetLibrary::InspectAnimationAsset(UAnimSequence* Sequence)
{
    if(!Sequence||!Sequence->GetSkeleton())return TEXT("{}");
    TSharedRef<FJsonObject> Object=MakeShared<FJsonObject>();
    const FTransform Motion=Sequence->ExtractRootMotionFromRange(0,Sequence->GetPlayLength(),FAnimExtractContext(Sequence->GetPlayLength(),true));
    const FTransform Ref=Sequence->GetSkeleton()->GetReferenceSkeleton().GetRefBonePose()[0];
    Object->SetArrayField(TEXT("extracted_root_motion_cm"),{MakeShared<FJsonValueNumber>(Motion.GetLocation().X),MakeShared<FJsonValueNumber>(Motion.GetLocation().Y),MakeShared<FJsonValueNumber>(Motion.GetLocation().Z)});
    const FRotator Rot=Ref.Rotator();
    Object->SetArrayField(TEXT("reference_root_rotation_degrees"),{MakeShared<FJsonValueNumber>(Rot.Pitch),MakeShared<FJsonValueNumber>(Rot.Yaw),MakeShared<FJsonValueNumber>(Rot.Roll)});
    Object->SetNumberField(TEXT("duration"),Sequence->GetPlayLength());
    FString Text;FJsonSerializer::Serialize(Object,TJsonWriterFactory<>::Create(&Text));return Text;
}

FString UMorphAssetLibrary::InspectBootSurface(USkeletalMesh* Mesh)
{
    TSharedRef<FJsonObject> Object=MakeShared<FJsonObject>();
    TArray<TSharedPtr<FJsonValue>> Vertices;
#if WITH_EDITOR
    if(Mesh && Mesh->GetResourceForRendering() && Mesh->GetResourceForRendering()->LODRenderData.Num())
    {
        const FSkeletalMeshLODRenderData& L=Mesh->GetResourceForRendering()->LODRenderData[0];
        const FSkinWeightVertexBuffer& Skin=*L.GetSkinWeightVertexBuffer();
        Object->SetStringField(TEXT("asset"),Mesh->GetPathName());Object->SetNumberField(TEXT("lod"),0);
        for(const FSkelMeshRenderSection& Section:L.RenderSections)for(uint32 V=Section.BaseVertexIndex;V<Section.BaseVertexIndex+Section.NumVertices;++V)
        {
            const FVector3f P=L.StaticVertexBuffers.PositionVertexBuffer.VertexPosition(V);
            if(P.Z < -.05 || P.Z > 18.2 || P.X < -7 || P.X > 21 || FMath::Abs(FMath::Abs(P.Y)-11)>7)continue;
            TSharedRef<FJsonObject> Item=MakeShared<FJsonObject>();
            Item->SetNumberField(TEXT("vertex"),V);Item->SetNumberField(TEXT("side"),P.Y>0?0:1);
            Item->SetArrayField(TEXT("position_cm"),{MakeShared<FJsonValueNumber>(P.X),MakeShared<FJsonValueNumber>(P.Y),MakeShared<FJsonValueNumber>(P.Z)});
            TArray<TSharedPtr<FJsonValue>> Bones,Weights;
            for(uint32 I=0;I<Skin.GetMaxBoneInfluences();++I)
            {
                const uint16 Weight=Skin.GetBoneWeight(V,I);if(!Weight)continue;
                Bones.Add(MakeShared<FJsonValueNumber>(Section.BoneMap[Skin.GetBoneIndex(V,I)]));
                Weights.Add(MakeShared<FJsonValueNumber>(double(Weight)/65535.));
            }
            Item->SetArrayField(TEXT("bone_indices"),Bones);Item->SetArrayField(TEXT("weights"),Weights);Vertices.Add(MakeShared<FJsonValueObject>(Item));
        }
    }
#endif
    Object->SetArrayField(TEXT("vertices"),Vertices);
    FString Text;FJsonSerializer::Serialize(Object,TJsonWriterFactory<>::Create(&Text));return Text;
}
