#include "OperativeImportLibrary.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/SkeletalMeshSocket.h"

bool UOperativeImportLibrary::AddOrReplaceSocket(USkeletalMesh* Mesh, FName SocketName, FName BoneName, const FTransform& RelativeTransform)
{
#if WITH_EDITOR
	if (!Mesh || SocketName.IsNone() || BoneName.IsNone()) return false;
	if (Mesh->GetRefSkeleton().FindBoneIndex(BoneName) == INDEX_NONE) return false;
	Mesh->Modify();
	TArray<TObjectPtr<USkeletalMeshSocket>>& List = Mesh->GetMeshOnlySocketList();
	for (int32 I = List.Num() - 1; I >= 0; --I)
	{
		if (List[I] && List[I]->SocketName == SocketName) List.RemoveAt(I);
	}
	USkeletalMeshSocket* S = NewObject<USkeletalMeshSocket>(Mesh);
	S->SocketName = SocketName;
	S->BoneName = BoneName;
	S->RelativeLocation = RelativeTransform.GetLocation();
	S->RelativeRotation = RelativeTransform.Rotator();
	S->RelativeScale = RelativeTransform.GetScale3D();
	Mesh->AddSocket(S, false);
	Mesh->MarkPackageDirty();
	return true;
#else
	return false;   // editing socket lists is an import time operation (the packaged client does not need it)
#endif
}

int32 UOperativeImportLibrary::CountMeshSockets(USkeletalMesh* Mesh)
{
	return Mesh ? Mesh->GetMeshOnlySocketList().Num() : 0;
}
