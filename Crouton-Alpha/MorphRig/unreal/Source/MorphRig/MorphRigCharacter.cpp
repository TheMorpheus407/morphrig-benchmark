// Copyright Epic Games, Inc. All Rights Reserved.

#include "MorphRigCharacter.h"
#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/SpringArmComponent.h"
#include "GameFramework/Controller.h"
#include "EnhancedInputComponent.h"
#include "InputActionValue.h"
#include "MorphRig.h"

AMorphRigCharacter::AMorphRigCharacter()
{
	GetCapsuleComponent()->InitCapsuleSize(42.f, 96.0f);
	bUseControllerRotationPitch = false;
	bUseControllerRotationYaw = false;
	bUseControllerRotationRoll = false;
	GetCharacterMovement()->bOrientRotationToMovement = true;
	GetCharacterMovement()->RotationRate = FRotator(0.0f, 500.0f, 0.0f);
	GetCharacterMovement()->JumpZVelocity = 500.f;
	GetCharacterMovement()->AirControl = 0.35f;
	GetCharacterMovement()->MaxWalkSpeed = 400.f;
	GetCharacterMovement()->MinAnalogWalkSpeed = 20.f;
	GetCharacterMovement()->BrakingDecelerationWalking = 2000.f;
	GetCharacterMovement()->BrakingDecelerationFalling = 1500.0f;

	CameraBoom = CreateDefaultSubobject<USpringArmComponent>(TEXT("CameraBoom"));
	CameraBoom->SetupAttachment(RootComponent);
	CameraBoom->TargetArmLength = 400.0f;
	CameraBoom->bUsePawnControlRotation = true;

	FollowCamera = CreateDefaultSubobject<UCameraComponent>(TEXT("FollowCamera"));
	FollowCamera->SetupAttachment(CameraBoom, USpringArmComponent::SocketName);
	FollowCamera->bUsePawnControlRotation = false;
}

void AMorphRigCharacter::BeginPlay()
{
	Super::BeginPlay();
	DemoSequence = {
		TEXT("idle_combat"), TEXT("walk_f"), TEXT("run_fr"), TEXT("melee_1"),
		TEXT("ranged_fire"), TEXT("reload"), TEXT("channel_start"), TEXT("channel_loop"),
		TEXT("channel_interrupt"), TEXT("hit_f"), TEXT("stun_start"), TEXT("stun_end"),
		TEXT("dash_f"), TEXT("jump_start"), TEXT("jump_air"), TEXT("jump_land"),
		TEXT("dialogue"), TEXT("victory")
	};
	LogTrace(TEXT("BeginPlay: showcase ready, clips=") + FString::FromInt(DemoSequence.Num()));
	GetWorldTimerManager().SetTimer(TraceTimer, this, &AMorphRigCharacter::StepDemo, 1.0f, true);
}

void AMorphRigCharacter::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
	if (UEnhancedInputComponent* EIC = Cast<UEnhancedInputComponent>(PlayerInputComponent))
	{
		EIC->BindAction(JumpAction, ETriggerEvent::Started, this, &ACharacter::Jump);
		EIC->BindAction(JumpAction, ETriggerEvent::Completed, this, &ACharacter::StopJumping);
		EIC->BindAction(MoveAction, ETriggerEvent::Triggered, this, &AMorphRigCharacter::Move);
		EIC->BindAction(MouseLookAction, ETriggerEvent::Triggered, this, &AMorphRigCharacter::Look);
		EIC->BindAction(LookAction, ETriggerEvent::Triggered, this, &AMorphRigCharacter::Look);
	}
	else
	{
		UE_LOG(LogMorphRig, Error, TEXT("Enhanced Input component missing"));
	}
}

void AMorphRigCharacter::Move(const FInputActionValue& Value)
{
	FVector2D V = Value.Get<FVector2D>();
	DoMove(V.X, V.Y);
}

void AMorphRigCharacter::Look(const FInputActionValue& Value)
{
	FVector2D V = Value.Get<FVector2D>();
	DoLook(V.X, V.Y);
}

void AMorphRigCharacter::DoMove(float Right, float Forward)
{
	if (GetController() != nullptr)
	{
		FRotator Rot = GetController()->GetControlRotation();
		FRotator YawRot(0, Rot.Yaw, 0);
		FVector Fwd = FRotationMatrix(YawRot).GetUnitAxis(EAxis::X);
		FVector Rgt = FRotationMatrix(YawRot).GetUnitAxis(EAxis::Y);
		AddMovementInput(Fwd, Forward);
		AddMovementInput(Rgt, Right);
	}
}

void AMorphRigCharacter::DoLook(float Yaw, float Pitch)
{
	if (GetController() != nullptr)
	{
		AddControllerYawInput(Yaw);
		AddControllerPitchInput(Pitch);
	}
}

void AMorphRigCharacter::DoJumpStart() { Jump(); }
void AMorphRigCharacter::DoJumpEnd() { StopJumping(); }

void AMorphRigCharacter::PlayNamedClip(const FString& ClipId)
{
	CurrentClip = ClipId;
	CurrentState = TEXT("Browser");
	bInterruptPending = false;
	LogTrace(TEXT("Play clip: ") + ClipId);
	UE_LOG(LogMorphRig, Log, TEXT("PlayNamedClip: %s"), *ClipId);
}

void AMorphRigCharacter::ResetCharacter()
{
	SetActorLocation(FVector::ZeroVector);
	SetActorRotation(FRotator::ZeroRotator);
	PlayNamedClip(TEXT("idle_combat"));
	CurrentState = TEXT("Reset");
	LogTrace(TEXT("Reset character"));
}

void AMorphRigCharacter::SetAim(float YawDeg, float PitchDeg)
{
	AimYaw = YawDeg; AimPitch = PitchDeg;
	LogTrace(FString::Printf(TEXT("Aim yaw=%.1f pitch=%.1f"), YawDeg, PitchDeg));
}

void AMorphRigCharacter::SetPlaybackSpeed(float Speed)
{
	PlaybackSpeed = FMath::Clamp(Speed, 0.5f, 1.5f);
	LogTrace(FString::Printf(TEXT("Playback speed %.2f"), PlaybackSpeed));
}

void AMorphRigCharacter::SetTeamVariant(int32 Variant)
{
	TeamVariant = Variant;
	LogTrace(FString::Printf(TEXT("Team variant %d"), Variant));
}

void AMorphRigCharacter::SetLOD(int32 Index)
{
	LODIndex = Index;
	GetMesh()->SetForcedLOD(Index);
	LogTrace(FString::Printf(TEXT("LOD %d"), Index));
}

void AMorphRigCharacter::SetCameraMode(int32 Mode)
{
	if (CameraBoom && FollowCamera)
	{
		switch (Mode)
		{
		case 0: CameraBoom->TargetArmLength = 400.f; break;
		case 1: CameraBoom->TargetArmLength = 250.f; break;
		case 2: CameraBoom->TargetArmLength = 600.f; FollowCamera->SetRelativeRotation(FRotator(-80.f, 0.f, 0.f)); break;
		case 3: CameraBoom->TargetArmLength = 80.f; break;
		}
		if (Mode != 2) FollowCamera->SetRelativeRotation(FRotator::ZeroRotator);
	}
	LogTrace(FString::Printf(TEXT("Camera mode %d"), Mode));
}

void AMorphRigCharacter::SetFaceControl(float Value, int32 ControlIndex)
{
	LogTrace(FString::Printf(TEXT("Face control %d = %.2f"), ControlIndex, Value));
}

void AMorphRigCharacter::RunDeterministicSequence()
{
	DemoIndex = 0;
	GetWorldTimerManager().SetTimer(DemoTimer, this, &AMorphRigCharacter::StepDemo, 0.8f, true);
	LogTrace(TEXT("Deterministic sequence started"));
}

void AMorphRigCharacter::StepDemo()
{
	if (DemoIndex >= DemoSequence.Num())
	{
		GetWorldTimerManager().ClearTimer(DemoTimer);
		LogTrace(TEXT("Deterministic sequence finished"));
		return;
	}
	PlayNamedClip(DemoSequence[DemoIndex++]);
}

void AMorphRigCharacter::ToggleInstanceCount()
{
	if (Allies.Num() == 0)
	{
		if (UWorld* World = GetWorld())
		{
			FActorSpawnParameters Params;
			for (int32 i = 0; i < 9; ++i)
			{
				FTransform T(FRotator::ZeroRotator, FVector(200.f + i * 100.f, 200.f, 0.f));
				if (AActor* A = World->SpawnActor<AActor>(GetClass(), T, Params))
				{
					Allies.Add(A);
				}
			}
		}
		LogTrace(TEXT("Instance toggle: spawned allies (10 total)"));
	}
	else
	{
		for (TWeakObjectPtr<AActor>& Ally : Allies)
		{
			if (Ally.IsValid()) Ally->Destroy();
		}
		Allies.Empty();
		LogTrace(TEXT("Instance toggle: removed allies (1 total)"));
	}
}

void AMorphRigCharacter::InterruptAction()
{
	bInterruptPending = true;
	CurrentState = TEXT("Interrupted");
	LogTrace(TEXT("Action interrupted (no teleport to start pose)"));
}

FString AMorphRigCharacter::GetStateTrace() const
{
	return FString::Join(TraceBuffer, TEXT(" | "));
}

void AMorphRigCharacter::LogTrace(const FString& Msg)
{
	TraceBuffer.Add(FString::Printf(TEXT("[%s] %s"), *FDateTime::Now().ToString(TEXT("%H:%M:%S")), *Msg));
	if (TraceBuffer.Num() > 200) TraceBuffer.RemoveAt(0, 100);
	UE_LOG(LogMorphRig, Log, TEXT("%s"), *Msg);
}
