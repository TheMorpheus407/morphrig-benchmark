#include "MorphRigEditorHelpers.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/SkeletalMeshSocket.h"
#include "Animation/Skeleton.h"
#include "Animation/AnimSequence.h"
#include "Animation/MorphTarget.h"

FString UMorphRigEditorHelpers::FinalizeOperativeAssets(
	USkeletalMesh* SkelMesh,
	UAnimSequence* IdleCombatSeq,
	const TArray<UAnimSequence*>& HitSeqs)
{
#if WITH_EDITOR
	if (!SkelMesh)
	{
		return TEXT("{\"error\": \"Null SkelMesh\"}");
	}

	struct FSocketSpec
	{
		const TCHAR* SocketName;
		const TCHAR* BoneName;
		FVector OffsetCm;
	};

	static const FSocketSpec SocketSpecs[] = {
		{ TEXT("socket_hand_r"),         TEXT("hand_r"),           FVector(0.0f, 0.0f, 0.0f) },
		{ TEXT("socket_hand_l"),         TEXT("hand_l"),           FVector(0.0f, 0.0f, 0.0f) },
		{ TEXT("socket_emitter_muzzle"), TEXT("emitter_muzzle"),   FVector(0.0f, 0.0f, 0.0f) },
		{ TEXT("socket_blade_base"),     TEXT("blade_r"),          FVector(0.0f, 0.0f, 0.0f) },
		{ TEXT("socket_blade_tip"),      TEXT("blade_tip"),        FVector(0.0f, 0.0f, 0.0f) },
		{ TEXT("socket_cell_slot"),      TEXT("emitter_bone_r"),   FVector(-3.5f, -2.4f, 0.0f) },
		{ TEXT("socket_beacon_dock"),    TEXT("pelvis"),           FVector(-10.5f, 12.3f, -2.5f) },
		{ TEXT("socket_chest_fx"),       TEXT("spine_03"),         FVector(0.0f, -12.0f, 4.0f) },
		{ TEXT("socket_head_fx"),        TEXT("head"),             FVector(0.0f, 0.0f, 26.0f) },
		{ TEXT("socket_root_fx"),        TEXT("root"),             FVector(0.0f, 0.0f, 2.0f) }
	};

	SkelMesh->Modify();
	SkelMesh->GetMeshOnlySocketList().Empty();
	if (USkeleton* Skel = SkelMesh->GetSkeleton())
	{
		Skel->Modify();
		Skel->Sockets.Empty();
	}

	const FReferenceSkeleton& RefSkelForSockets = SkelMesh->GetRefSkeleton();
	FVector RootRefScale(1.0f, 1.0f, 1.0f);
	if (RefSkelForSockets.GetNum() > 0)
	{
		RootRefScale = RefSkelForSockets.GetRefBonePose()[0].GetScale3D();
	}
	const float InvBoneScale = (FMath::Abs(RootRefScale.X) > 1e-3f) ? (1.0f / RootRefScale.X) : 1.0f;

	for (const FSocketSpec& Spec : SocketSpecs)
	{
		USkeletalMeshSocket* MeshSock = NewObject<USkeletalMeshSocket>(SkelMesh);
		MeshSock->SocketName = FName(Spec.SocketName);
		MeshSock->BoneName = FName(Spec.BoneName);
		MeshSock->RelativeLocation = Spec.OffsetCm * InvBoneScale;
		MeshSock->RelativeRotation = FRotator::ZeroRotator;
		MeshSock->RelativeScale = FVector(InvBoneScale);
		MeshSock->bForceAlwaysAnimated = true;
		SkelMesh->AddSocket(MeshSock, /*bAddToSkeleton=*/true);
	}
	SkelMesh->RebuildSocketMap();

	// Configure LOD screen sizes: LOD0 = 1.0, LOD1 = 0.45, LOD2 = 0.20
	const float ScreenSizes[3] = { 1.0f, 0.45f, 0.20f };
	const int32 NumLODs = SkelMesh->GetLODNum();
	for (int32 LodIdx = 0; LodIdx < FMath::Min(NumLODs, 3); ++LodIdx)
	{
		if (FSkeletalMeshLODInfo* LodInfo = SkelMesh->GetLODInfo(LodIdx))
		{
			LodInfo->ScreenSize.Default = ScreenSizes[LodIdx];
		}
	}

	SkelMesh->PostEditChange();
	SkelMesh->MarkPackageDirty();
	if (USkeleton* Skel = SkelMesh->GetSkeleton())
	{
		for (UMorphTarget* MT : SkelMesh->GetMorphTargets())
		{
			if (MT)
			{
				Skel->AddCurveMetaData(MT->GetFName(), false);
				Skel->SetCurveMetaDataMorphTarget(MT->GetFName(), true);
			}
		}
		Skel->PostEditChange();
		Skel->MarkPackageDirty();
	}

	// Configure Local-Space Additive Hit Sequences relative to Anim_idle_combat frame 0
	int32 ConfiguredHits = 0;
	for (UAnimSequence* HitSeq : HitSeqs)
	{
		if (!HitSeq)
		{
			continue;
		}
		HitSeq->Modify();
		HitSeq->AdditiveAnimType = AAT_LocalSpaceBase;
		if (IdleCombatSeq)
		{
			HitSeq->RefPoseType = ABPT_AnimFrame;
			HitSeq->RefPoseSeq = IdleCombatSeq;
			HitSeq->RefFrameIndex = 0;
		}
		else
		{
			HitSeq->RefPoseType = ABPT_RefPose;
		}
		HitSeq->PostEditChange();
		HitSeq->MarkPackageDirty();
		ConfiguredHits++;
	}

	const FBox Box = SkelMesh->GetImportedBounds().GetBox();
	const float HeightCm = Box.Max.Z - Box.Min.Z;
	const FReferenceSkeleton& RefSkel = SkelMesh->GetRefSkeleton();
	const FString RootName = (RefSkel.GetNum() > 0) ? RefSkel.GetBoneName(0).ToString() : TEXT("NONE");

	return FString::Printf(
		TEXT("{\"standing_height_cm\": %.3f, \"min_z_cm\": %.3f, \"max_z_cm\": %.3f, \"root_bone\": \"%s\", \"num_bones\": %d, \"num_morph_targets\": %d, \"num_lods\": %d, \"num_sockets\": %d, \"num_materials\": %d, \"configured_additive_hits\": %d}"),
		HeightCm,
		Box.Min.Z,
		Box.Max.Z,
		*RootName,
		RefSkel.GetNum(),
		SkelMesh->GetMorphTargets().Num(),
		SkelMesh->GetLODNum(),
		SkelMesh->NumSockets(),
		SkelMesh->GetMaterials().Num(),
		ConfiguredHits);
#else
	return TEXT("{}");
#endif
}
