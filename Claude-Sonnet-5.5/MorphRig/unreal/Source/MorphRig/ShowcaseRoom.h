// MORPHRIG: the showcase room (20 degree ramp, steps up to 20 cm, movable aim targets, prop contact station and motion viewer pedestal)
// with a three light rig that follows the camera yaw (key from the upper left, fill from the right, rim from behind) so every view and the
// turntable stay readable. Studio mode hides the test props and shows a plain floor and backdrop (turntable and face captures).
// Everything is built from engine basic shapes at BeginPlay, so the map only contains this actor and a PlayerStart.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "ShowcaseRoom.generated.h"

class UStaticMeshComponent;
class UMaterialInstanceDynamic;
class UMaterialInterface;
class UStaticMesh;
class UTextRenderComponent;
class UPrimitiveComponent;
class UDirectionalLightComponent;
class AShowcaseTarget;
class UOperativeAssets;

/** Aim target: reacts to shots and blade hits, can patrol and be moved by the user. */
UCLASS()
class MORPHRIG_API AShowcaseTarget : public AActor
{
	GENERATED_BODY()
public:
	AShowcaseTarget();
	virtual void Tick(float DeltaSeconds) override;
	void Setup(UStaticMesh* Sphere, UStaticMesh* Cylinder, UMaterialInterface* Material, const FVector& InHome, float Height, int32 InIndex);
	void RegisterHit(const FVector& Location);
	void SetPatrol(bool bOn, float Amplitude = 250.f, float Speed = 0.6f);
	void MoveHome(const FVector& NewHome);
	void SetSelected(bool b);
	int32 GetHitCount() const { return HitCount; }
	int32 GetIndex() const { return Index; }
	FVector GetHome() const { return Home; }
	float GetHeight() const { return TargetHeight; }

private:
	UPROPERTY() TObjectPtr<UStaticMeshComponent> Ball;
	UPROPERTY() TObjectPtr<UStaticMeshComponent> Stand;
	UPROPERTY() TObjectPtr<UTextRenderComponent> Label;
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> BallMID;
	FVector Home = FVector::ZeroVector;
	float TargetHeight = 120.f;
	int32 Index = 0;
	int32 HitCount = 0;
	float FlashTimer = 0.f;
	bool bPatrol = false;
	float PatrolAmp = 250.f, PatrolSpeed = 0.6f, PatrolTime = 0.f;
	bool bSelected = false;
};

UCLASS()
class MORPHRIG_API AShowcaseRoom : public AActor
{
	GENERATED_BODY()
public:
	AShowcaseRoom();
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	const TArray<TObjectPtr<AShowcaseTarget>>& GetTargets() const { return Targets; }
	void SetTargetsPatrol(bool bOn);
	void SetTargetsShown(bool bShown) { for (AShowcaseTarget* T : Targets) if (T) T->SetActorHiddenInGame(!bShown); }     // visibility only, the colliders stay
	bool GetTargetsPatrol() const { return bTargetsPatrol; }
	/** Moves the selected target (cycled with SelectNextTarget) to a world position on the floor. */
	void MoveSelectedTarget(const FVector& WorldPoint);
	void SelectNextTarget();
	AShowcaseTarget* GetSelectedTarget() const { return Targets.IsValidIndex(SelectedTarget) ? Targets[SelectedTarget].Get() : nullptr; }
	int32 TotalTargetHits() const;
	/** Plain floor and backdrop without ramp, steps, stations, labels and targets. */
	void SetStudioMode(bool bOn);
	void SetFaceLighting(bool bOn);        // frontal, softer key for the face close-up (a side key throws the nose shadow across the mouth)
	void SetWallsHiddenForView(bool bHide);   // the top-down view looks over the room walls: their dark inner faces fill the frame, so they are hidden there
	void SetViewerBackdropShown(bool bShow);   // the wall behind the motion viewer pedestal, shown only while the viewer is open
	bool IsStudioMode() const { return bStudio; }

	FVector GetSpawnPoint() const { return FVector(0.f, 0.f, 92.f); }
	FVector GetViewerPedestal() const { return ViewerPedestal; }
	FVector GetPropStation() const { return PropStation; }
	FVector GetRampBottom() const { return RampBottom; }
	FVector GetStairsBottom() const { return StairsBottom; }
	FVector GetSmallStepsStart() const { return SmallStepsStart; }
	FVector GetPlatformTop() const { return PlatformTop; }

private:
	UStaticMeshComponent* AddBox(const FName& Name, const FVector& Center, const FVector& Size, const FRotator& Rot, UMaterialInterface* Mat, bool bShadow = true);
	UStaticMeshComponent* AddCylinder(const FName& Name, const FVector& Center, float Radius, float Height, UMaterialInterface* Mat);
	void AddLabel(const FString& Text, const FVector& Location, const FRotator& Rotation, float Size, FColor Color);
	void BuildLights();
	void BuildGeometry();
	void UpdateLightRig(float CameraYaw);

	UPROPERTY() TObjectPtr<UOperativeAssets> Assets;
	UPROPERTY() TArray<TObjectPtr<AShowcaseTarget>> Targets;
	UPROPERTY() TObjectPtr<UStaticMesh> Cube;
	UPROPERTY() TObjectPtr<UStaticMesh> Cylinder;
	UPROPERTY() TObjectPtr<UMaterialInterface> FloorMat;
	UPROPERTY() TObjectPtr<UMaterialInterface> WallMat;
	UPROPERTY() TObjectPtr<UMaterialInterface> PropMat;
	UPROPERTY() TObjectPtr<UMaterialInterface> StudioFloorMat;
	UPROPERTY() TObjectPtr<UMaterialInterface> StudioWallMat;
	UPROPERTY() TObjectPtr<UStaticMeshComponent> FloorComp;
	UPROPERTY() TObjectPtr<UStaticMeshComponent> StudioBackdrop;
	UPROPERTY() TObjectPtr<UStaticMeshComponent> HorizonDome;
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> WallComps;
	UPROPERTY() TArray<TObjectPtr<UPrimitiveComponent>> PropComps;      // hidden in studio mode
	UPROPERTY() TObjectPtr<UDirectionalLightComponent> KeyLight;
	UPROPERTY() TObjectPtr<UDirectionalLightComponent> FillLight;
	UPROPERTY() TObjectPtr<UDirectionalLightComponent> RimLight;

	FVector ViewerPedestal = FVector(-520.f, 0.f, 0.f);
	FVector PropStation = FVector(260.f, 380.f, 0.f);
	FVector RampBottom = FVector(-700.f, -900.f, 0.f);
	FVector StairsBottom = FVector(-400.f, 700.f, 0.f);
	FVector SmallStepsStart = FVector(-1000.f, -300.f, 0.f);
	FVector PlatformTop = FVector(300.f, -900.f, 300.f);
	int32 SelectedTarget = 0;
	bool bTargetsPatrol = false;
	int32 CompCounter = 0;
	UPROPERTY() TArray<TObjectPtr<class UTextRenderComponent>> UprightLabels;     // vertical labels turn to face the camera (text renders mirrored from behind)
	bool bStudio = false;
	bool bBuildingProps = false;
	float AppliedLightYaw = 1000.f;
	bool bFaceLighting = false;
	bool bWallsHiddenForView = false;
	UPROPERTY() TObjectPtr<UStaticMeshComponent> ViewerBackdropComp;
	void ApplyWallVisibility();
};
