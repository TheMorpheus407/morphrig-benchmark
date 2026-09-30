#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "Animation/AnimNotifies/AnimNotify.h"
#include "MorphOperative.generated.h"

class UAnimSequence;
class UAudioComponent;
class UMaterialInstanceDynamic;
class UMorphAnimInstance;
class AStaticMeshActor;

UCLASS()
class MORPHRIG_API UMorphMarkerNotify : public UAnimNotify
{
    GENERATED_BODY()
public:
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="MorphRig") FName EventName;
    virtual FString GetNotifyName_Implementation() const override { return EventName.ToString(); }
};

struct FMorphMarker { float Time = 0; FString Name; };
struct FMorphClip
{
    FName Id;
    FString Form, Layer, RootPolicy;
    float Duration = 1, Speed = 0;
    bool bLoop = false, bPose = false;
    TArray<FMorphMarker> Markers;
};
struct FMorphTrack
{
    FName Id;
    float Time = 0, PreviousTime = -0.001f;
    int32 Token = 0, Cycle = 0;
    bool bActive = false;
};

UCLASS()
class MORPHRIG_API AMorphOperative : public ACharacter
{
    GENERATED_BODY()
public:
    AMorphOperative();
    virtual void BeginPlay() override;
    virtual void Tick(float Delta) override;
    virtual void Landed(const FHitResult& Hit) override;
    bool Request(FName Id, bool bBrowser = false);
    void ReleaseState(bool bCancel);
    void ResetOperative();
    void SetTeam(int32 Team);
    void SetLOD(int32 LOD);
    void SetMaterialMode(int32 Mode);
    void SetFace(FName Name, float Value);
    void SetExpression(int32 Index);
    void FaceReset();
    void SetMoveInput(FVector2D Value, int32 SpeedMode);
    void SetDisable(FName Name);
    void SetAim(float Yaw, float Pitch);
    void Trace(const FString& What);
    UAnimSequence* Sequence(FName Id) const;
    const FMorphClip* Clip(FName Id) const;
    FString StateText() const;
    void AdvanceTrack(FMorphTrack& Track, float Delta, bool bRoot);
    void ProcessMarker(const FMorphTrack& Track, const FMorphMarker& Marker);
    void CompleteTrack(FMorphTrack& Track);
    void BuildPose(float Delta);
    void LoadLibrary();

    UPROPERTY() TMap<FName, TObjectPtr<UAnimSequence>> Sequences;
    UPROPERTY() TArray<TObjectPtr<UMaterialInstanceDynamic>> Materials;
    UPROPERTY() TObjectPtr<UAudioComponent> Voice;
    UPROPERTY() TObjectPtr<AStaticMeshActor> DeployedBeacon;
    TMap<FName, FMorphClip> Clips;
    TArray<FName> Inventory;
    TArray<FString> RecentEvents;
    FMorphTrack Body, Upper, HitTrack, GaitTrack;
    FVector2D MoveInput = FVector2D::ZeroVector;
    int32 SpeedMode = 0, TeamIndex = 0, ForcedLOD = 0, MaterialMode = 0;
    float Rate = 1, AimYaw = 0, AimPitch = 0, LocomotionPhase = 0;
    float TransitionAge = 1, UpperWeight = 0, LastVerticalSpeed = 0;
    float FacingCompensation = 0;
    FVector LastGaitActorLocation = FVector::ZeroVector;
    FName LastBaseId;
    bool bHaveGaitLocation = false, bStationaryContacts = false, bUpperSnapshot = false;
    int32 Serial = 0, NextToken = 1;
    int32 ResetSerial = 0;
    bool bWounded = false, bDead = false, bStasis = false;
    bool bRooted = false, bSilenced = false, bDisarmed = false;
    bool bSkeletonOverlay = false, bBrowserMode = false, bFaceOverride = false;
    bool bAimEnabled = false;
    FName AttentionState;
    TMap<FName, float> FaceControls;
    FVector BlinkDestination = FVector::ZeroVector;
    FVector StasisVelocity = FVector::ZeroVector;
    FVector AttentionTarget = FVector(450,-180,100);
    FVector FootTarget[2] = {FVector::ZeroVector, FVector::ZeroVector};
    FVector FootNormal[2] = {FVector::UpVector, FVector::UpVector};
    float FootWeight[2] = {0, 0}, PelvisOffset = 0;
    FString TracePath;
};
